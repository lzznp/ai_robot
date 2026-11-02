#include "application.h"
#include "board.h"
#include "display.h"
#include "system_info.h"
#include "audio_codec.h"
#include "mqtt_protocol.h"
#include "websocket_protocol.h"
#include "assets/lang_config.h"
#include "mcp_server.h"
#include "assets.h"
#include "settings.h"
#include "code_interpreter.h"
#include <cstring>
#include <esp_log.h>
#include <cJSON.h>
#include <driver/gpio.h>
#include <driver/ledc.h>
#include <led_strip.h>
#include <arpa/inet.h>
#include <font_awesome.h>


#define TAG "Application"


static const char* const STATE_STRINGS[] = {
    "unknown",
    "starting",
    "configuring",
    "idle",
    "connecting",
    "listening",
    "speaking",
    "upgrading",
    "activating",
    "audio_testing",
    "fatal_error",
    "invalid_state"
};

Application::Application() {
    event_group_ = xEventGroupCreate();

#if CONFIG_USE_DEVICE_AEC && CONFIG_USE_SERVER_AEC
#error "CONFIG_USE_DEVICE_AEC and CONFIG_USE_SERVER_AEC cannot be enabled at the same time"
#elif CONFIG_USE_DEVICE_AEC
    aec_mode_ = kAecOnDeviceSide;
#elif CONFIG_USE_SERVER_AEC
    aec_mode_ = kAecOnServerSide;
#else
    aec_mode_ = kAecOff;
#endif

    esp_timer_create_args_t clock_timer_args = {
        .callback = [](void* arg) {
            Application* app = (Application*)arg;
            xEventGroupSetBits(app->event_group_, MAIN_EVENT_CLOCK_TICK);
        },
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "clock_timer",
        .skip_unhandled_events = true
    };
    esp_timer_create(&clock_timer_args, &clock_timer_handle_);
}

Application::~Application() {
    if (clock_timer_handle_ != nullptr) {
        esp_timer_stop(clock_timer_handle_);
        esp_timer_delete(clock_timer_handle_);
    }
    vEventGroupDelete(event_group_);
}

void Application::CheckAssetsVersion() {
    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();
    auto& assets = Assets::GetInstance();

    if (!assets.partition_valid()) {
        ESP_LOGW(TAG, "Assets partition is disabled for board %s", BOARD_NAME);
        return;
    }
    
    Settings settings("assets", true);
    // Check if there is a new assets need to be downloaded
    std::string download_url = settings.GetString("download_url");

    if (!download_url.empty()) {
        settings.EraseKey("download_url");

        char message[256];
        snprintf(message, sizeof(message), Lang::Strings::FOUND_NEW_ASSETS, download_url.c_str());
        Alert(Lang::Strings::LOADING_ASSETS, message, "cloud_arrow_down", Lang::Sounds::OGG_UPGRADE);
        
        // Wait for the audio service to be idle for 3 seconds
        vTaskDelay(pdMS_TO_TICKS(3000));
        SetDeviceState(kDeviceStateUpgrading);
        board.SetPowerSaveMode(false);
        display->SetChatMessage("system", Lang::Strings::PLEASE_WAIT);

        bool success = assets.Download(download_url, [display](int progress, size_t speed) -> void {
            std::thread([display, progress, speed]() {
                char buffer[32];
                snprintf(buffer, sizeof(buffer), "%d%% %uKB/s", progress, speed / 1024);
                display->SetChatMessage("system", buffer);
            }).detach();
        });

        board.SetPowerSaveMode(true);
        vTaskDelay(pdMS_TO_TICKS(1000));

        if (!success) {
            Alert(Lang::Strings::ERROR, Lang::Strings::DOWNLOAD_ASSETS_FAILED, "circle_xmark", Lang::Sounds::OGG_EXCLAMATION);
            vTaskDelay(pdMS_TO_TICKS(2000));
            return;
        }
    }

    // Apply assets
    assets.Apply();
    display->SetChatMessage("system", "");
    display->SetEmotion("microchip_ai");
}

void Application::CheckNewVersion(Ota& ota) {
    const int MAX_RETRY = 10;
    int retry_count = 0;
    int retry_delay = 10; // 初始重试延迟为10秒

    auto& board = Board::GetInstance();
    while (true) {
        SetDeviceState(kDeviceStateActivating);
        auto display = board.GetDisplay();
        display->SetStatus(Lang::Strings::CHECKING_NEW_VERSION);

        esp_err_t err = ota.CheckVersion();
        if (err != ESP_OK) {
            retry_count++;
            if (retry_count >= MAX_RETRY) {
                ESP_LOGE(TAG, "Too many retries, exit version check");
                return;
            }

            char error_message[128];
            snprintf(error_message, sizeof(error_message), "code=%d, url=%s", err, ota.GetCheckVersionUrl().c_str());
            char buffer[256];
            snprintf(buffer, sizeof(buffer), Lang::Strings::CHECK_NEW_VERSION_FAILED, retry_delay, error_message);
            Alert(Lang::Strings::ERROR, buffer, "cloud_slash", Lang::Sounds::OGG_EXCLAMATION);

            ESP_LOGW(TAG, "Check new version failed, retry in %d seconds (%d/%d)", retry_delay, retry_count, MAX_RETRY);
            for (int i = 0; i < retry_delay; i++) {
                vTaskDelay(pdMS_TO_TICKS(1000));
                if (device_state_ == kDeviceStateIdle) {
                    break;
                }
            }
            retry_delay *= 2; // 每次重试后延迟时间翻倍
            continue;
        }
        retry_count = 0;
        retry_delay = 10; // 重置重试延迟时间

        if (ota.HasNewVersion()) {
            if (UpgradeFirmware(ota)) {
                return; // This line will never be reached after reboot
            }
            // If upgrade failed, continue to normal operation (don't break, just fall through)
        }

        // No new version, mark the current version as valid
        ota.MarkCurrentVersionValid();
        if (!ota.HasActivationCode() && !ota.HasActivationChallenge()) {
            xEventGroupSetBits(event_group_, MAIN_EVENT_CHECK_NEW_VERSION_DONE);
            // Exit the loop if done checking new version
            break;
        }

        display->SetStatus(Lang::Strings::ACTIVATION);
        // Activation code is shown to the user and waiting for the user to input
        if (ota.HasActivationCode()) {
            ShowActivationCode(ota.GetActivationCode(), ota.GetActivationMessage());
        }

        // This will block the loop until the activation is done or timeout
        for (int i = 0; i < 10; ++i) {
            ESP_LOGI(TAG, "Activating... %d/%d", i + 1, 10);
            esp_err_t err = ota.Activate();
            if (err == ESP_OK) {
                xEventGroupSetBits(event_group_, MAIN_EVENT_CHECK_NEW_VERSION_DONE);
                break;
            } else if (err == ESP_ERR_TIMEOUT) {
                vTaskDelay(pdMS_TO_TICKS(3000));
            } else {
                vTaskDelay(pdMS_TO_TICKS(10000));
            }
            if (device_state_ == kDeviceStateIdle) {
                break;
            }
        }
    }
}

void Application::ShowActivationCode(const std::string& code, const std::string& message) {
    struct digit_sound {
        char digit;
        const std::string_view& sound;
    };
    static const std::array<digit_sound, 10> digit_sounds{{
        digit_sound{'0', Lang::Sounds::OGG_0},
        digit_sound{'1', Lang::Sounds::OGG_1}, 
        digit_sound{'2', Lang::Sounds::OGG_2},
        digit_sound{'3', Lang::Sounds::OGG_3},
        digit_sound{'4', Lang::Sounds::OGG_4},
        digit_sound{'5', Lang::Sounds::OGG_5},
        digit_sound{'6', Lang::Sounds::OGG_6},
        digit_sound{'7', Lang::Sounds::OGG_7},
        digit_sound{'8', Lang::Sounds::OGG_8},
        digit_sound{'9', Lang::Sounds::OGG_9}
    }};

    // This sentence uses 9KB of SRAM, so we need to wait for it to finish
    Alert(Lang::Strings::ACTIVATION, message.c_str(), "link", Lang::Sounds::OGG_ACTIVATION);

    for (const auto& digit : code) {
        auto it = std::find_if(digit_sounds.begin(), digit_sounds.end(),
            [digit](const digit_sound& ds) { return ds.digit == digit; });
        if (it != digit_sounds.end()) {
            audio_service_.PlaySound(it->sound);
        }
    }
}

void Application::Alert(const char* status, const char* message, const char* emotion, const std::string_view& sound) {
    ESP_LOGW(TAG, "Alert [%s] %s: %s", emotion, status, message);
    auto display = Board::GetInstance().GetDisplay();
    display->SetStatus(status);
    display->SetEmotion(emotion);
    display->SetChatMessage("system", message);
    if (!sound.empty()) {
        audio_service_.PlaySound(sound);
    }
}

void Application::DismissAlert() {
    if (device_state_ == kDeviceStateIdle) {
        auto display = Board::GetInstance().GetDisplay();
        display->SetStatus(Lang::Strings::STANDBY);
        display->SetEmotion("neutral");
        display->SetChatMessage("system", "");
    }
}

void Application::ToggleChatState() {
    if (device_state_ == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
        return;
    } else if (device_state_ == kDeviceStateWifiConfiguring) {
        audio_service_.EnableAudioTesting(true);
        SetDeviceState(kDeviceStateAudioTesting);
        return;
    } else if (device_state_ == kDeviceStateAudioTesting) {
        audio_service_.EnableAudioTesting(false);
        SetDeviceState(kDeviceStateWifiConfiguring);
        return;
    }

    if (!protocol_) {
        ESP_LOGE(TAG, "Protocol not initialized");
        return;
    }

    if (device_state_ == kDeviceStateIdle) {
        Schedule([this]() {
            if (!protocol_->IsAudioChannelOpened()) {
                SetDeviceState(kDeviceStateConnecting);
                if (!protocol_->OpenAudioChannel()) {
                    return;
                }
            }

            SetListeningMode(aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime);
        });
    } else if (device_state_ == kDeviceStateSpeaking) {
        Schedule([this]() {
            AbortSpeaking(kAbortReasonNone);
        });
    } else if (device_state_ == kDeviceStateListening) {
        Schedule([this]() {
            protocol_->CloseAudioChannel();
        });
    }
}

void Application::StartListening() {
    if (device_state_ == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
        return;
    } else if (device_state_ == kDeviceStateWifiConfiguring) {
        audio_service_.EnableAudioTesting(true);
        SetDeviceState(kDeviceStateAudioTesting);
        return;
    }

    if (!protocol_) {
        ESP_LOGE(TAG, "Protocol not initialized");
        return;
    }
    
    if (device_state_ == kDeviceStateIdle) {
        Schedule([this]() {
            if (!protocol_->IsAudioChannelOpened()) {
                SetDeviceState(kDeviceStateConnecting);
                if (!protocol_->OpenAudioChannel()) {
                    return;
                }
            }

            SetListeningMode(kListeningModeManualStop);
        });
    } else if (device_state_ == kDeviceStateSpeaking) {
        Schedule([this]() {
            AbortSpeaking(kAbortReasonNone);
            SetListeningMode(kListeningModeManualStop);
        });
    }
}

void Application::StopListening() {
    if (device_state_ == kDeviceStateAudioTesting) {
        audio_service_.EnableAudioTesting(false);
        SetDeviceState(kDeviceStateWifiConfiguring);
        return;
    }

    const std::array<int, 3> valid_states = {
        kDeviceStateListening,
        kDeviceStateSpeaking,
        kDeviceStateIdle,
    };
    // If not valid, do nothing
    if (std::find(valid_states.begin(), valid_states.end(), device_state_) == valid_states.end()) {
        return;
    }

    Schedule([this]() {
        if (device_state_ == kDeviceStateListening) {
            protocol_->SendStopListening();
            SetDeviceState(kDeviceStateIdle);
        }
    });
}

void Application::Start() {
    auto& board = Board::GetInstance();
    SetDeviceState(kDeviceStateStarting);

    /* Setup the display */
    auto display = board.GetDisplay();

    // Print board name/version info
    display->SetChatMessage("system", SystemInfo::GetUserAgent().c_str());

    /* Setup the audio service */
    auto codec = board.GetAudioCodec();
    audio_service_.Initialize(codec);
    audio_service_.Start();


    AudioServiceCallbacks callbacks;
    callbacks.on_send_queue_available = [this]() {
        xEventGroupSetBits(event_group_, MAIN_EVENT_SEND_AUDIO);
    };
    callbacks.on_wake_word_detected = [this](const std::string& wake_word) {
        xEventGroupSetBits(event_group_, MAIN_EVENT_WAKE_WORD_DETECTED);
    };
    callbacks.on_vad_change = [this](bool speaking) {
        xEventGroupSetBits(event_group_, MAIN_EVENT_VAD_CHANGE);
    };
    audio_service_.SetCallbacks(callbacks);

    // Start the main event loop task with priority 3
    xTaskCreate([](void* arg) {
        ((Application*)arg)->MainEventLoop();
        vTaskDelete(NULL);
    }, "main_event_loop", 2048 * 4, this, 3, &main_event_loop_task_handle_);

    /* Start the clock timer to update the status bar */


     // ★ 新增：初始化任务定时器
    esp_timer_create_args_t task_timer_args = {
        .callback = Application::TaskTimerCallback,
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "task_timer",
        .skip_unhandled_events = true
    };
    esp_timer_create(&task_timer_args, &task_timer_handle_);
    esp_timer_start_periodic(clock_timer_handle_, 1000000);

    /* Wait for the network to be ready */
    board.StartNetwork();

    // Update the status bar immediately to show the network state
    display->UpdateStatusBar(true);

    // Check for new assets version
    CheckAssetsVersion();

    // Check for new firmware version or get the MQTT broker address
    Ota ota;
    CheckNewVersion(ota);

    // Initialize the protocol
    display->SetStatus(Lang::Strings::LOADING_PROTOCOL);

    // Add MCP common tools before initializing the protocol
    auto& mcp_server = McpServer::GetInstance();
    mcp_server.AddCommonTools();
    mcp_server.AddUserOnlyTools();

    if (ota.HasMqttConfig()) {
        protocol_ = std::make_unique<MqttProtocol>();
    } else if (ota.HasWebsocketConfig()) {
        protocol_ = std::make_unique<WebsocketProtocol>();
    } else {
        ESP_LOGW(TAG, "No protocol specified in the OTA config, using MQTT");
        protocol_ = std::make_unique<MqttProtocol>();
    }

    protocol_->OnConnected([this]() {
        DismissAlert();
    });

    protocol_->OnNetworkError([this](const std::string& message) {
        last_error_message_ = message;
        xEventGroupSetBits(event_group_, MAIN_EVENT_ERROR);
    });
    protocol_->OnIncomingAudio([this](std::unique_ptr<AudioStreamPacket> packet) {
    AudioStreamPacket* raw_packet = packet.release();
    Schedule([this, raw_packet]() {
        std::unique_ptr<AudioStreamPacket> p(raw_packet);
        // ★ 直接接受所有音频数据，不再检查状态
        audio_service_.PushPacketToDecodeQueue(std::move(p));
        ESP_LOGI("TTS", "✅ ACCEPT audio packet (command channel)");
    });
});
    protocol_->OnAudioChannelOpened([this, codec, &board]() {
        board.SetPowerSaveMode(false);
        if (protocol_->server_sample_rate() != codec->output_sample_rate()) {
            ESP_LOGW(TAG, "Server sample rate %d does not match device output sample rate %d, resampling may cause distortion",
                protocol_->server_sample_rate(), codec->output_sample_rate());
        }
    });
    protocol_->OnAudioChannelClosed([this, &board]() {
        board.SetPowerSaveMode(true);
        Schedule([this]() {
            auto display = Board::GetInstance().GetDisplay();
            display->SetChatMessage("system", "");
            SetDeviceState(kDeviceStateIdle);
        });
    });
    protocol_->OnIncomingJson([this, display](const cJSON* root) {

    // ★★★ 打印所有收到的消息（调试用） ★★★
    char* json_str = cJSON_PrintUnformatted(root);
    ESP_LOGI(TAG, "📩 OnIncomingJson: %s", json_str);
    free(json_str);

    // Parse JSON data
    auto type = cJSON_GetObjectItem(root, "type");
    if (strcmp(type->valuestring, "tts") == 0) {
        auto state = cJSON_GetObjectItem(root, "state");
        if (strcmp(state->valuestring, "start") == 0) {
            ESP_LOGI("TTS", "[TTS] state: start");
            Schedule([this]() {
                aborted_ = false;
                if (device_state_ == kDeviceStateIdle || device_state_ == kDeviceStateListening) {
                    SetDeviceState(kDeviceStateSpeaking);
                }
            });
        } else if (strcmp(state->valuestring, "stop") == 0) {
            ESP_LOGI("TTS", "[TTS] state: stop");
            Schedule([this]() {
                if (device_state_ == kDeviceStateSpeaking) {
                    if (listening_mode_ == kListeningModeManualStop) {
                        SetDeviceState(kDeviceStateIdle);
                    } else {
                        SetDeviceState(kDeviceStateListening);
                    }
                }
            });
        } else if (strcmp(state->valuestring, "sentence_start") == 0) {
            auto text = cJSON_GetObjectItem(root, "text");
            if (cJSON_IsString(text)) {
                ESP_LOGI("TTS", "[TTS] sentence_start: %s", text->valuestring);
                Schedule([this, display, message = std::string(text->valuestring)]() {
                    display->SetChatMessage("assistant", message.c_str());
                });
            }
        }
    } else if (strcmp(type->valuestring, "stt") == 0) {
        auto text = cJSON_GetObjectItem(root, "text");
        if (cJSON_IsString(text)) {
            ESP_LOGI(TAG, ">> %s", text->valuestring);
            Schedule([this, display, message = std::string(text->valuestring)]() {
                display->SetChatMessage("user", message.c_str());
            });
        }
    } else if (strcmp(type->valuestring, "llm") == 0) {
        auto emotion = cJSON_GetObjectItem(root, "emotion");
        if (cJSON_IsString(emotion)) {
            Schedule([this, display, emotion_str = std::string(emotion->valuestring)]() {
                display->SetEmotion(emotion_str.c_str());
            });
        }
    } else if (strcmp(type->valuestring, "mcp") == 0) {
        auto payload = cJSON_GetObjectItem(root, "payload");
        if (cJSON_IsObject(payload)) {
            McpServer::GetInstance().ParseMessage(payload);
        }
    // ★★★★★★★ 运动指令处理 (action) ★★★★★★★
    } else if (strcmp(type->valuestring, "action") == 0) {
        auto action = cJSON_GetObjectItem(root, "action");
        if (!cJSON_IsString(action)) {
            ESP_LOGW(TAG, "Invalid action: missing or not a string");
            return;
        }

        auto params = cJSON_GetObjectItem(root, "params");
        auto& board = Board::GetInstance();
        std::string action_str = action->valuestring;

        ESP_LOGI(TAG, "📩 Action: %s", action_str.c_str());

        if (action_str == "move_forward") {
            board.MoveForward();
        } else if (action_str == "move_backward") {
            board.MoveBackward();
        } else if (action_str == "turn_left") {
            board.TurnLeft();
        } else if (action_str == "turn_right") {
            board.TurnRight();
        } else if (action_str == "stop") {
            board.Stop();
        } else if (action_str == "wave") {
            board.Wave();
        } else if (action_str == "servo") {
            if (params) {
                auto angle = cJSON_GetObjectItem(params, "angle");
                if (angle && cJSON_IsNumber(angle)) {
                    board.SetServoAngle(angle->valueint);
                    ESP_LOGI(TAG, "  Servo angle: %d", angle->valueint);
                } else {
                    ESP_LOGW(TAG, "  Missing or invalid 'angle' parameter");
                }
            } else {
                ESP_LOGW(TAG, "  Missing 'params' for servo action");
            }
        } else {
            ESP_LOGW(TAG, "Unknown action: %s", action_str.c_str());
        }

    // ★★★★★★★ 新增：代码流执行 (code_stream) ★★★★★★★
    } else if (strcmp(type->valuestring, "code_stream") == 0) {
        auto steps = cJSON_GetObjectItem(root, "steps");
        if (!cJSON_IsArray(steps)) {
            ESP_LOGW(TAG, "Invalid code_stream: 'steps' is not an array");
            return;
        }

        ESP_LOGI(TAG, "📥 Received code_stream with %d steps", cJSON_GetArraySize(steps));

        // 复制 steps，因为回调执行完后 root 可能被释放
        cJSON* steps_copy = cJSON_Duplicate(steps, true);
        if (!steps_copy) {
            ESP_LOGE(TAG, "Failed to duplicate steps");
            return;
        }

        Schedule([this, steps_copy]() {
            CodeInterpreter::Execute(steps_copy);
            cJSON_Delete(steps_copy);
        });

    // ============================================================
    // ★★★★★★★ 新增：我们自己的纯净指令通道 (command) ★★★★★★★
    // ============================================================
    } else if (strcmp(type->valuestring, "command") == 0) {
        auto payload = cJSON_GetObjectItem(root, "payload");
        if (!cJSON_IsObject(payload)) {
            ESP_LOGW(TAG, "[Command] 无效指令: 缺少 payload");
            return;
        }

        ESP_LOGI(TAG, "🎬 [Command] 收到新指令");
        char* payload_str = cJSON_PrintUnformatted(payload);
        ESP_LOGI(TAG, "📦 Payload: %s", payload_str);
        free(payload_str);

        Schedule([this, payload = cJSON_Duplicate(payload, true)]() {
            ExecuteCommand(payload);
            cJSON_Delete(payload);
        });

    } else if (strcmp(type->valuestring, "system") == 0) {
        auto command = cJSON_GetObjectItem(root, "command");
        if (cJSON_IsString(command)) {
            ESP_LOGI(TAG, "System command: %s", command->valuestring);
            if (strcmp(command->valuestring, "reboot") == 0) {
                Schedule([this]() {
                    Reboot();
                });
            } else {
                ESP_LOGW(TAG, "Unknown system command: %s", command->valuestring);
            }
        }
    } else if (strcmp(type->valuestring, "alert") == 0) {
        auto status = cJSON_GetObjectItem(root, "status");
        auto message = cJSON_GetObjectItem(root, "message");
        auto emotion = cJSON_GetObjectItem(root, "emotion");
        if (cJSON_IsString(status) && cJSON_IsString(message) && cJSON_IsString(emotion)) {
            Alert(status->valuestring, message->valuestring, emotion->valuestring, Lang::Sounds::OGG_VIBRATION);
        } else {
            ESP_LOGW(TAG, "Alert command requires status, message and emotion");
        }
#if CONFIG_RECEIVE_CUSTOM_MESSAGE
    } else if (strcmp(type->valuestring, "custom") == 0) {
        auto payload = cJSON_GetObjectItem(root, "payload");
        ESP_LOGI(TAG, "Received custom message: %s", cJSON_PrintUnformatted(root));
        if (cJSON_IsObject(payload)) {
            Schedule([this, display, payload_str = std::string(cJSON_PrintUnformatted(payload))]() {
                display->SetChatMessage("system", payload_str.c_str());
            });
        } else {
            ESP_LOGW(TAG, "Invalid custom message format: missing payload");
        }
#endif
    } else {
        ESP_LOGW(TAG, "Unknown message type: %s", type->valuestring);
    }
});
        bool protocol_started = protocol_->Start();

    SystemInfo::PrintHeapStats();
    SetDeviceState(kDeviceStateIdle);

    has_server_time_ = ota.HasServerTime();
    if (protocol_started) {
        std::string message = std::string(Lang::Strings::VERSION) + ota.GetCurrentVersion();
        display->ShowNotification(message.c_str());
        display->SetChatMessage("system", "");
        // Play the success sound to indicate the device is ready
        audio_service_.PlaySound(Lang::Sounds::OGG_SUCCESS);

        // ========== 新增：自动建立 WebSocket 连接 ==========
        ESP_LOGI(TAG, "Device ready, auto-connecting to server...");
        // 延迟 1 秒确保所有服务完全就绪
        vTaskDelay(pdMS_TO_TICKS(1000));
        // 自动打开 WebSocket 通道（相当于模拟按键唤醒）
        ToggleChatState();
        // ====================================================
    }
}

// Add a async task to MainLoop
void Application::Schedule(std::function<void()> callback) {
    {
        std::unique_lock<std::mutex> lock(mutex_);
        main_tasks_.push_back(std::move(callback));
    }
    xEventGroupSetBits(event_group_, MAIN_EVENT_SCHEDULE);
}

// The Main Event Loop controls the chat state and websocket connection
// If other tasks need to access the websocket or chat state,
// they should use Schedule to call this function
void Application::MainEventLoop() {
    while (true) {
        auto bits = xEventGroupWaitBits(event_group_, MAIN_EVENT_SCHEDULE |
            MAIN_EVENT_SEND_AUDIO |
            MAIN_EVENT_WAKE_WORD_DETECTED |
            MAIN_EVENT_VAD_CHANGE |
            MAIN_EVENT_CLOCK_TICK |
            MAIN_EVENT_ERROR, pdTRUE, pdFALSE, portMAX_DELAY);

        if (bits & MAIN_EVENT_ERROR) {
            SetDeviceState(kDeviceStateIdle);
            Alert(Lang::Strings::ERROR, last_error_message_.c_str(), "circle_xmark", Lang::Sounds::OGG_EXCLAMATION);
        }

        if (bits & MAIN_EVENT_SEND_AUDIO) {
            while (auto packet = audio_service_.PopPacketFromSendQueue()) {
                if (protocol_ && !protocol_->SendAudio(std::move(packet))) {
                    break;
                }
            }
        }

        if (bits & MAIN_EVENT_WAKE_WORD_DETECTED) {
            OnWakeWordDetected();
        }

        if (bits & MAIN_EVENT_VAD_CHANGE) {
            if (device_state_ == kDeviceStateListening) {
                auto led = Board::GetInstance().GetLed();
                led->OnStateChanged();
            }
        }

        if (bits & MAIN_EVENT_SCHEDULE) {
            std::unique_lock<std::mutex> lock(mutex_);
            auto tasks = std::move(main_tasks_);
            lock.unlock();
            for (auto& task : tasks) {
                task();
            }
        }

        if (bits & MAIN_EVENT_CLOCK_TICK) {
            clock_ticks_++;
            auto display = Board::GetInstance().GetDisplay();
            display->UpdateStatusBar();
        
            // Print the debug info every 10 seconds
            if (clock_ticks_ % 10 == 0) {
                // SystemInfo::PrintTaskCpuUsage(pdMS_TO_TICKS(1000));
                // SystemInfo::PrintTaskList();
                SystemInfo::PrintHeapStats();
            }
        }
    }
}

void Application::OnWakeWordDetected() {
    if (!protocol_) {
        return;
    }

    if (device_state_ == kDeviceStateIdle) {
        audio_service_.EncodeWakeWord();

        if (!protocol_->IsAudioChannelOpened()) {
            SetDeviceState(kDeviceStateConnecting);
            if (!protocol_->OpenAudioChannel()) {
                audio_service_.EnableWakeWordDetection(true);
                return;
            }
        }

        auto wake_word = audio_service_.GetLastWakeWord();
        ESP_LOGI(TAG, "Wake word detected: %s", wake_word.c_str());
#if CONFIG_SEND_WAKE_WORD_DATA
        // Encode and send the wake word data to the server
        while (auto packet = audio_service_.PopWakeWordPacket()) {
            protocol_->SendAudio(std::move(packet));
        }
        // Set the chat state to wake word detected
        protocol_->SendWakeWordDetected(wake_word);
        SetListeningMode(aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime);
#else
        SetListeningMode(aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime);
        // Play the pop up sound to indicate the wake word is detected
        audio_service_.PlaySound(Lang::Sounds::OGG_POPUP);
#endif
    } else if (device_state_ == kDeviceStateSpeaking) {
        AbortSpeaking(kAbortReasonWakeWordDetected);
    } else if (device_state_ == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
    }
}

void Application::AbortSpeaking(AbortReason reason) {
    ESP_LOGI(TAG, "Abort speaking");
    aborted_ = true;
    if (protocol_) {
        protocol_->SendAbortSpeaking(reason);
    }
}

void Application::SetListeningMode(ListeningMode mode) {
    listening_mode_ = mode;
    SetDeviceState(kDeviceStateListening);
}

void Application::SetDeviceState(DeviceState state) {
    if (device_state_ == state) {
        return;
    }
    
    clock_ticks_ = 0;
    auto previous_state = device_state_;
    device_state_ = state;
    ESP_LOGI(TAG, "STATE: %s", STATE_STRINGS[device_state_]);

    // Send the state change event
    DeviceStateEventManager::GetInstance().PostStateChangeEvent(previous_state, state);

    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();
    auto led = board.GetLed();
    led->OnStateChanged();
    switch (state) {
        case kDeviceStateUnknown:
        case kDeviceStateIdle:
            display->SetStatus(Lang::Strings::STANDBY);
            display->SetEmotion("neutral");
            audio_service_.EnableVoiceProcessing(false);
            audio_service_.EnableWakeWordDetection(true);
            break;
        case kDeviceStateConnecting:
            display->SetStatus(Lang::Strings::CONNECTING);
            display->SetEmotion("neutral");
            display->SetChatMessage("system", "");
            break;
        case kDeviceStateListening:
            display->SetStatus(Lang::Strings::LISTENING);
            display->SetEmotion("neutral");

            // Make sure the audio processor is running
            if (!audio_service_.IsAudioProcessorRunning()) {
                // Send the start listening command
                protocol_->SendStartListening(listening_mode_);
                audio_service_.EnableVoiceProcessing(true);
                audio_service_.EnableWakeWordDetection(false);
            }
            break;
        case kDeviceStateSpeaking:
    display->SetStatus(Lang::Strings::SPEAKING);
    if (listening_mode_ != kListeningModeRealtime) {
        audio_service_.EnableVoiceProcessing(false);
        audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
    }
    // 只在从非 Speaking 状态进入时清空，避免跨句误清空
    if (previous_state != kDeviceStateSpeaking) {
        audio_service_.ResetDecoder();
    }
    break;
        default:
            // Do nothing
            break;
    }
}

void Application::Reboot() {
    ESP_LOGI(TAG, "Rebooting...");
    // Disconnect the audio channel
    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        protocol_->CloseAudioChannel();
    }
    protocol_.reset();
    audio_service_.Stop();

    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();
}

bool Application::UpgradeFirmware(Ota& ota, const std::string& url) {
    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();
    
    // Use provided URL or get from OTA object
    std::string upgrade_url = url.empty() ? ota.GetFirmwareUrl() : url;
    std::string version_info = url.empty() ? ota.GetFirmwareVersion() : "(Manual upgrade)";
    
    // Close audio channel if it's open
    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        ESP_LOGI(TAG, "Closing audio channel before firmware upgrade");
        protocol_->CloseAudioChannel();
    }
    ESP_LOGI(TAG, "Starting firmware upgrade from URL: %s", upgrade_url.c_str());
    
    Alert(Lang::Strings::OTA_UPGRADE, Lang::Strings::UPGRADING, "download", Lang::Sounds::OGG_UPGRADE);
    vTaskDelay(pdMS_TO_TICKS(3000));

    SetDeviceState(kDeviceStateUpgrading);
    
    std::string message = std::string(Lang::Strings::NEW_VERSION) + version_info;
    display->SetChatMessage("system", message.c_str());

    board.SetPowerSaveMode(false);
    audio_service_.Stop();
    vTaskDelay(pdMS_TO_TICKS(1000));

    bool upgrade_success = ota.StartUpgradeFromUrl(upgrade_url, [display](int progress, size_t speed) {
        std::thread([display, progress, speed]() {
            char buffer[32];
            snprintf(buffer, sizeof(buffer), "%d%% %uKB/s", progress, speed / 1024);
            display->SetChatMessage("system", buffer);
        }).detach();
    });

    if (!upgrade_success) {
        // Upgrade failed, restart audio service and continue running
        ESP_LOGE(TAG, "Firmware upgrade failed, restarting audio service and continuing operation...");
        audio_service_.Start(); // Restart audio service
        board.SetPowerSaveMode(true); // Restore power save mode
        Alert(Lang::Strings::ERROR, Lang::Strings::UPGRADE_FAILED, "circle_xmark", Lang::Sounds::OGG_EXCLAMATION);
        vTaskDelay(pdMS_TO_TICKS(3000));
        return false;
    } else {
        // Upgrade success, reboot immediately
        ESP_LOGI(TAG, "Firmware upgrade successful, rebooting...");
        display->SetChatMessage("system", "Upgrade successful, rebooting...");
        vTaskDelay(pdMS_TO_TICKS(1000)); // Brief pause to show message
        Reboot();
        return true;
    }
}

void Application::WakeWordInvoke(const std::string& wake_word) {
    if (!protocol_) {
        return;
    }

    if (device_state_ == kDeviceStateIdle) {
        audio_service_.EncodeWakeWord();

        if (!protocol_->IsAudioChannelOpened()) {
            SetDeviceState(kDeviceStateConnecting);
            if (!protocol_->OpenAudioChannel()) {
                audio_service_.EnableWakeWordDetection(true);
                return;
            }
        }

        ESP_LOGI(TAG, "Wake word detected: %s", wake_word.c_str());
#if CONFIG_USE_AFE_WAKE_WORD || CONFIG_USE_CUSTOM_WAKE_WORD
        // Encode and send the wake word data to the server
        while (auto packet = audio_service_.PopWakeWordPacket()) {
            protocol_->SendAudio(std::move(packet));
        }
        // Set the chat state to wake word detected
        protocol_->SendWakeWordDetected(wake_word);
        SetListeningMode(aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime);
#else
        SetListeningMode(aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime);
        // Play the pop up sound to indicate the wake word is detected
        audio_service_.PlaySound(Lang::Sounds::OGG_POPUP);
#endif
    } else if (device_state_ == kDeviceStateSpeaking) {
        Schedule([this]() {
            AbortSpeaking(kAbortReasonNone);
        });
    } else if (device_state_ == kDeviceStateListening) {   
        Schedule([this]() {
            if (protocol_) {
                protocol_->CloseAudioChannel();
            }
        });
    }
}

bool Application::CanEnterSleepMode() {
    if (device_state_ != kDeviceStateIdle) {
        return false;
    }

    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        return false;
    }

    if (!audio_service_.IsIdle()) {
        return false;
    }

    // Now it is safe to enter sleep mode
    return true;
}

void Application::SendMcpMessage(const std::string& payload) {
    if (protocol_ == nullptr) {
        return;
    }

    // Make sure you are using main thread to send MCP message
    if (xTaskGetCurrentTaskHandle() == main_event_loop_task_handle_) {
        protocol_->SendMcpMessage(payload);
    } else {
        Schedule([this, payload = std::move(payload)]() {
            protocol_->SendMcpMessage(payload);
        });
    }
}

void Application::SetAecMode(AecMode mode) {
    aec_mode_ = mode;
    Schedule([this]() {
        auto& board = Board::GetInstance();
        auto display = board.GetDisplay();
        switch (aec_mode_) {
        case kAecOff:
            audio_service_.EnableDeviceAec(false);
            display->ShowNotification(Lang::Strings::RTC_MODE_OFF);
            break;
        case kAecOnServerSide:
            audio_service_.EnableDeviceAec(false);
            display->ShowNotification(Lang::Strings::RTC_MODE_ON);
            break;
        case kAecOnDeviceSide:
            audio_service_.EnableDeviceAec(true);
            display->ShowNotification(Lang::Strings::RTC_MODE_ON);
            break;
        }

        // If the AEC mode is changed, close the audio channel
        if (protocol_ && protocol_->IsAudioChannelOpened()) {
            protocol_->CloseAudioChannel();
        }
    });
}

void Application::PlaySound(const std::string_view& sound) {
    audio_service_.PlaySound(sound);
}

// ============================================================
// ★ 引脚级执行器（芯片级通用能力，与板子无关）
//
// 设计约定：固件**不认识**"前进 / 挥手 / 亮灯"这些词。
// 它只认识两件硬件事实：
//    gpio  某脚输出什么电平，保持多少毫秒
//    pwm   某脚输出什么频率 / 脉宽（或占空比），保持多少毫秒
// 语义（"前进"= 17 高 18 低 26 高 27 低，1.2 秒）由**后台能力库**定义成一串指令流，
// 换个板子只要换能力库里的引脚流，固件一行不用改。
// ============================================================
namespace {

constexpr uint32_t kLedcSrcClkHz = 80000000u;   // LEDC 取 APB 时钟

bool s_gpio_ready[64] = {false};                // 每根脚只配一次输出

// 把引脚配成输出（幂等）
bool EnsureOutput(int pin) {
    if (pin < 0 || pin >= 64) {
        return false;
    }
    if (s_gpio_ready[pin]) {
        return true;
    }
    gpio_config_t io = {};
    io.pin_bit_mask = (1ULL << pin);
    io.mode = GPIO_MODE_OUTPUT;
    io.pull_up_en = GPIO_PULLUP_DISABLE;
    io.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io.intr_type = GPIO_INTR_DISABLE;
    if (gpio_config(&io) != ESP_OK) {
        return false;
    }
    s_gpio_ready[pin] = true;
    return true;
}

// 分辨率 = log2(源时钟 / 频率)，上限 14 位、下限 8 位
int BitsForFreq(uint32_t freq) {
    if (freq == 0) {
        freq = 50;
    }
    uint32_t div = kLedcSrcClkHz / freq;
    int bits = 0;
    while (div > 1 && bits < 14) {
        div >>= 1;
        bits++;
    }
    return bits < 8 ? 8 : bits;
}

struct PwmPinEntry {
    int pin = -1;
    ledc_channel_t ch = LEDC_CHANNEL_0;
};

struct PwmTimerEntry {
    uint32_t freq = 0;
    ledc_timer_t timer = LEDC_TIMER_0;
    bool used = false;
};

constexpr int kMaxPwmPins = LEDC_CHANNEL_MAX;
PwmPinEntry s_pwm_pins[kMaxPwmPins];
PwmTimerEntry s_pwm_timers[LEDC_TIMER_MAX];

// 应用一路 PWM：脉宽模式（舵机）或占空比模式（调速）
bool ApplyPinPwm(int pin, uint32_t freq, int pulse_us, int duty_pct, bool use_duty) {
    if (pin < 0 || pin >= 64) {
        return false;
    }
    if (freq == 0) {
        freq = 50;
    }

    // 1) 找/分配该引脚的信道
    int idx = -1;
    for (int i = 0; i < kMaxPwmPins; i++) {
        if (s_pwm_pins[i].pin == pin) {
            idx = i;
            break;
        }
    }
    if (idx < 0) {
        for (int i = 0; i < kMaxPwmPins; i++) {
            if (s_pwm_pins[i].pin < 0) {
                idx = i;
                s_pwm_pins[i].pin = pin;
                s_pwm_pins[i].ch = (ledc_channel_t)i;
                break;
            }
        }
    }
    if (idx < 0) {
        ESP_LOGW(TAG, "[PWM] 信道已满，引脚 %d 申请失败", pin);
        return false;
    }

    // 2) 找/分配一个能出这个频率的定时器
    ledc_timer_t timer = LEDC_TIMER_MAX;
    for (int i = 0; i < LEDC_TIMER_MAX; i++) {
        if (s_pwm_timers[i].used && s_pwm_timers[i].freq == freq) {
            timer = s_pwm_timers[i].timer;
            break;
        }
    }
    if (timer == LEDC_TIMER_MAX) {
        for (int i = 0; i < LEDC_TIMER_MAX; i++) {
            if (!s_pwm_timers[i].used) {
                s_pwm_timers[i].used = true;
                s_pwm_timers[i].freq = freq;
                s_pwm_timers[i].timer = (ledc_timer_t)i;
                timer = (ledc_timer_t)i;
                break;
            }
        }
    }
    if (timer == LEDC_TIMER_MAX) {
        ESP_LOGW(TAG, "[PWM] 定时器已满，频率 %u 申请失败", (unsigned)freq);
        return false;
    }

    int bits = BitsForFreq(freq);
    ledc_timer_config_t tcfg = {};
    tcfg.speed_mode = LEDC_LOW_SPEED_MODE;
    tcfg.duty_resolution = (ledc_timer_bit_t)bits;
    tcfg.timer_num = timer;
    tcfg.freq_hz = freq;
    tcfg.clk_cfg = LEDC_AUTO_CLK;
    if (ledc_timer_config(&tcfg) != ESP_OK) {
        ESP_LOGW(TAG, "[PWM] 定时器配置失败 pin=%d freq=%u", pin, (unsigned)freq);
        return false;
    }

    uint32_t max_duty = (1u << bits) - 1u;
    uint32_t duty;
    if (use_duty) {
        duty = (uint32_t)((uint64_t)max_duty * (uint32_t)(duty_pct < 0 ? 0 : duty_pct) / 100u);
    } else {
        // 脉宽 -> 计数：ticks = pulse_us * freq * (max+1) / 1e6
        duty = (uint32_t)((uint64_t)(pulse_us < 0 ? 0 : pulse_us) * freq * (max_duty + 1u) / 1000000ull);
    }
    if (duty > max_duty) {
        duty = max_duty;
    }

    ledc_channel_config_t ccfg = {};
    ccfg.gpio_num = pin;
    ccfg.speed_mode = LEDC_LOW_SPEED_MODE;
    ccfg.channel = s_pwm_pins[idx].ch;
    ccfg.intr_type = LEDC_INTR_DISABLE;
    ccfg.timer_sel = timer;
    ccfg.duty = duty;
    ccfg.hpoint = 0;
    if (ledc_channel_config(&ccfg) != ESP_OK) {
        ESP_LOGW(TAG, "[PWM] 信道配置失败 pin=%d", pin);
        return false;
    }
    ESP_LOGI(TAG, "[PWM] pin=%d freq=%u %s=%d bits=%d duty=%u", pin, (unsigned)freq,
             use_duty ? "duty%" : "pulse_us", use_duty ? duty_pct : pulse_us, bits,
             (unsigned)duty);
    return true;
}

// 关掉该引脚的 PWM 输出（占空比归零）
void StopPinPwm(int pin) {
    for (int i = 0; i < kMaxPwmPins; i++) {
        if (s_pwm_pins[i].pin == pin) {
            ledc_set_duty(LEDC_LOW_SPEED_MODE, s_pwm_pins[i].ch, 0);
            ledc_update_duty(LEDC_LOW_SPEED_MODE, s_pwm_pins[i].ch);
            ESP_LOGI(TAG, "[PWM] pin=%d 停止输出", pin);
            return;
        }
    }
}

// ============================================================
// 芯片级 WS2812 灯带（RMT 输出，与上面 LEDC 的 PWM 通道互不冲突）
//
// 为什么单独做：WS2812/WS2812B 认的不是电平，是 800kHz 的 GRB 数据流。
// 用 gpio 打高电平对它毫无意义（试过就懂：灯纹丝不动）。
// 每条灯带按 (pin, count) 缓存一个 RMT 句柄，重复点亮不重复建。
// ============================================================
constexpr int kMaxWsStrips = 4;

struct WsStripEntry {
    int pin = -1;
    int count = 0;
    led_strip_handle_t handle = nullptr;
};

WsStripEntry s_ws_strips[kMaxWsStrips];

led_strip_handle_t EnsureStrip(int pin, int count) {
    if (pin < 0 || pin >= 64 || count <= 0 || count > 2048) {
        return nullptr;
    }
    for (int i = 0; i < kMaxWsStrips; i++) {
        if (s_ws_strips[i].handle != nullptr && s_ws_strips[i].pin == pin &&
            s_ws_strips[i].count == count) {
            return s_ws_strips[i].handle;
        }
    }
    led_strip_config_t cfg = {};
    cfg.strip_gpio_num = pin;
    cfg.max_leds = count;
    cfg.color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB;
    cfg.led_model = LED_MODEL_WS2812;

    led_strip_rmt_config_t rmt = {};
    rmt.resolution_hz = 10 * 1000 * 1000;   // 10MHz，和 SingleLed 一致

    led_strip_handle_t handle = nullptr;
    esp_err_t err = led_strip_new_rmt_device(&cfg, &rmt, &handle);
    if (err != ESP_OK || handle == nullptr) {
        ESP_LOGW(TAG, "[WS2812] 创建失败 pin=%d count=%d err=%s", pin, count,
                 esp_err_to_name(err));
        return nullptr;
    }
    for (int i = 0; i < kMaxWsStrips; i++) {
        if (s_ws_strips[i].handle == nullptr) {
            s_ws_strips[i].pin = pin;
            s_ws_strips[i].count = count;
            s_ws_strips[i].handle = handle;
            ESP_LOGI(TAG, "[WS2812] 新建灯带 pin=%d count=%d", pin, count);
            return handle;
        }
    }
    ESP_LOGW(TAG, "[WS2812] 灯带槽位已满(=%d)", kMaxWsStrips);
    led_strip_del(handle);
    return nullptr;
}

// 点亮：所有灯珠同一个颜色（r/g/b 各 0~255）
bool ApplyWs2812(int pin, int count, int r, int g, int b) {
    led_strip_handle_t handle = EnsureStrip(pin, count);
    if (handle == nullptr) {
        return false;
    }
    for (int i = 0; i < count; i++) {
        led_strip_set_pixel(handle, i, r, g, b);
    }
    if (led_strip_refresh(handle) != ESP_OK) {
        ESP_LOGW(TAG, "[WS2812] refresh 失败 pin=%d", pin);
        return false;
    }
    ESP_LOGI(TAG, "[WS2812] pin=%d count=%d rgb=(%d,%d,%d)", pin, count, r, g, b);
    return true;
}

}  // namespace

// ============================================================
// ★ 新增：Command 指令执行器实现
// ============================================================

void Application::ExecuteCommand(cJSON* payload) {
    // 1. 检查是否有 tts 指令
    auto tts_text = cJSON_GetObjectItem(payload, "tts");
    if (cJSON_IsString(tts_text)) {
        ESP_LOGI(TAG, "🔊 [Command] TTS: %s", tts_text->valuestring);
        PlayTtsDirectly(tts_text->valuestring);
    }

    // 2. 检查是否有 emotion 指令
    auto emotion = cJSON_GetObjectItem(payload, "emotion");
    if (cJSON_IsString(emotion)) {
        ESP_LOGI(TAG, "😊 [Command] Emotion: %s", emotion->valuestring);
        auto display = Board::GetInstance().GetDisplay();
        display->SetEmotion(emotion->valuestring);
        // 也加入队列，保证顺序
        TaskItem item;
        item.type = "emotion";
        item.emotion = emotion->valuestring;
        AppendTask(item);
    }

    // 3. 检查是否有 actions 数组
    auto actions = cJSON_GetObjectItem(payload, "actions");
    if (cJSON_IsArray(actions)) {
        int count = cJSON_GetArraySize(actions);
        ESP_LOGI(TAG, "🎬 [Command] 收到 %d 个动作", count);

        for (int i = 0; i < count; i++) {
            auto action = cJSON_GetArrayItem(actions, i);
            auto type = cJSON_GetObjectItem(action, "type");
            if (!cJSON_IsString(type)) continue;

            std::string action_type = type->valuestring;
            ESP_LOGI(TAG, "  [%d] Action: %s", i, action_type.c_str());

            TaskItem item;
            item.type = action_type;

            // --- TTS 动作 ---
            if (action_type == "tts") {
                auto text = cJSON_GetObjectItem(action, "text");
                if (cJSON_IsString(text)) {
                    item.text = text->valuestring;
                    AppendTask(item);
                }
            }
            // --- GPIO 控制（引脚级；可带保持时长，到点回低）---
            else if (action_type == "gpio") {
                auto pin = cJSON_GetObjectItem(action, "pin");
                auto level = cJSON_GetObjectItem(action, "level");
                if (cJSON_IsNumber(pin) && cJSON_IsNumber(level)) {
                    item.gpio_pin = pin->valueint;
                    item.gpio_level = level->valueint;
                    auto dur = cJSON_GetObjectItem(action, "duration");
                    if (cJSON_IsNumber(dur)) {
                        item.duration_ms = dur->valueint;
                    }
                    AppendTask(item);
                }
            }
            // --- 引脚级 PWM（舵机用 pulse_us，调速用 duty）---
            else if (action_type == "pwm") {
                auto pin = cJSON_GetObjectItem(action, "pin");
                if (cJSON_IsNumber(pin)) {
                    item.pwm_pin = pin->valueint;
                    auto freq = cJSON_GetObjectItem(action, "freq");
                    if (cJSON_IsNumber(freq)) {
                        item.pwm_freq_hz = freq->valueint;
                    }
                    auto pulse = cJSON_GetObjectItem(action, "pulse_us");
                    auto duty = cJSON_GetObjectItem(action, "duty");
                    if (cJSON_IsNumber(pulse)) {
                        item.pwm_use_duty = false;
                        item.pwm_pulse_us = pulse->valueint;
                    } else if (cJSON_IsNumber(duty)) {
                        item.pwm_use_duty = true;
                        item.pwm_duty_pct = duty->valueint;
                    }
                    auto dur = cJSON_GetObjectItem(action, "duration");
                    if (cJSON_IsNumber(dur)) {
                        item.duration_ms = dur->valueint;
                    }
                    AppendTask(item);
                }
            }
            // --- 舵机控制 ---
            else if (action_type == "servo") {
                auto angle = cJSON_GetObjectItem(action, "angle");
                if (cJSON_IsNumber(angle)) {
                    item.servo_angle = angle->valueint;
                    AppendTask(item);
                }
            }
            // --- 移动控制 ---
            else if (action_type == "move") {
                auto direction = cJSON_GetObjectItem(action, "direction");
                auto duration = cJSON_GetObjectItem(action, "duration");
                if (cJSON_IsString(direction)) {
                    item.move_dir = direction->valuestring;
                    if (cJSON_IsNumber(duration)) {
                        item.duration_ms = duration->valueint;
                    }
                    AppendTask(item);
                }
            }
            // --- 芯片级 WS2812 灯带（3 针 5V 灯带：G/V/S，S 接数据脚）---
            else if (action_type == "ws2812") {
                auto pin = cJSON_GetObjectItem(action, "pin");
                if (cJSON_IsNumber(pin)) {
                    item.ws_pin = pin->valueint;
                    auto count = cJSON_GetObjectItem(action, "count");
                    item.ws_count = cJSON_IsNumber(count) ? count->valueint : 1;

                    /* 颜色两种写法都收：
                     *   "rgb": [r, g, b]                 （推荐，一眼能看出是三色）
                     *   "r"/"g"/"b": 数值               （单色更省事）
                     * 全不给 = 关灯（rgb 全 0）。 */
                    auto rgb = cJSON_GetObjectItem(action, "rgb");
                    if (cJSON_IsArray(rgb) && cJSON_GetArraySize(rgb) >= 3) {
                        item.ws_r = cJSON_GetArrayItem(rgb, 0)->valueint;
                        item.ws_g = cJSON_GetArrayItem(rgb, 1)->valueint;
                        item.ws_b = cJSON_GetArrayItem(rgb, 2)->valueint;
                    } else {
                        auto r = cJSON_GetObjectItem(action, "r");
                        auto g = cJSON_GetObjectItem(action, "g");
                        auto b = cJSON_GetObjectItem(action, "b");
                        if (cJSON_IsNumber(r)) item.ws_r = r->valueint;
                        if (cJSON_IsNumber(g)) item.ws_g = g->valueint;
                        if (cJSON_IsNumber(b)) item.ws_b = b->valueint;
                    }

                    auto dur = cJSON_GetObjectItem(action, "duration");
                    if (cJSON_IsNumber(dur)) {
                        item.duration_ms = dur->valueint;
                    }
                    AppendTask(item);
                }
            }
            // --- 摄像头（芯片级触发：抓一帧 / 抓帧并上传视觉接口）---
            else if (action_type == "camera") {
                auto op = cJSON_GetObjectItem(action, "op");
                item.cam_op = cJSON_IsString(op) ? op->valuestring : "capture";
                AppendTask(item);
            }
            // --- 步进电机（芯片级：走 N 步；不是"左转/抬头"这种语义）---
            else if (action_type == "stepper") {
                auto motor = cJSON_GetObjectItem(action, "motor");
                auto steps = cJSON_GetObjectItem(action, "steps");
                if (cJSON_IsNumber(motor) && cJSON_IsNumber(steps)) {
                    item.st_motor = motor->valueint;
                    item.st_steps = steps->valueint;
                    auto sp = cJSON_GetObjectItem(action, "speed");
                    if (cJSON_IsNumber(sp)) {
                        item.st_speed_hz = sp->valueint;
                    }
                    /* release: true（缺省）= 走完断电松劲（现有行为）
                     *          false    = 保持力矩（悬挂机构怕重力下垂时用） */
                    auto rel = cJSON_GetObjectItem(action, "release");
                    if (cJSON_IsBool(rel)) {
                        item.st_hold = !cJSON_IsTrue(rel);
                    }
                    AppendTask(item);
                } else {
                    ESP_LOGW(TAG, "  [%d] stepper 缺少 motor/steps", i);
                }
            }
            // --- 延时 ---
            else if (action_type == "delay") {
                auto duration = cJSON_GetObjectItem(action, "duration");
                if (cJSON_IsNumber(duration)) {
                    item.duration_ms = duration->valueint;
                    AppendTask(item);
                }
            }
            // --- 表情 ---
            else if (action_type == "emotion") {
                auto emo = cJSON_GetObjectItem(action, "emotion");
                if (cJSON_IsString(emo)) {
                    item.emotion = emo->valuestring;
                    AppendTask(item);
                }
            }
            // --- 未知动作 ---
            else {
                ESP_LOGW(TAG, "  [%d] 未知动作类型: %s", i, action_type.c_str());
            }
        }
    }
}

void Application::PlayTtsDirectly(const std::string& text) {
    ESP_LOGI(TAG, "🔊 [PlayTtsDirectly] 播放: %s", text.c_str());

    // ★ 这里需要调用 TTS 服务生成音频
    // 暂时用占位实现，后续对接后台 TTS
    //
    // 实际实现中，你需要：
    // 1. 通过 WebSocket 请求后台生成 TTS 音频
    // 2. 收到音频数据后，直接 PushPacketToDecodeQueue
    //
    // 示例：模拟一个音频包
    // auto packet = std::make_unique<AudioStreamPacket>();
    // packet->sample_rate = 24000;
    // packet->frame_duration = 60;
    // packet->payload = ...; // Opus 数据
    // audio_service_.PushPacketToDecodeQueue(std::move(packet));
}

void Application::AppendTask(const TaskItem& task) {
    std::unique_lock<std::mutex> lock(mutex_);
    task_queue_.push(task);
    bool should_process = !task_running_;
    if (should_process) {
        task_running_ = true;
    }
    lock.unlock();  // ← 释放锁

    if (should_process) {
        ProcessNextTask();
    }
}

void Application::ProcessNextTask() {
    ESP_LOGI(TAG, "📋 [TaskQueue] ProcessNextTask 进入");

    ESP_LOGI(TAG, "📋 [TaskQueue] 尝试获取锁...");
    std::unique_lock<std::mutex> lock(mutex_);
    ESP_LOGI(TAG, "📋 [TaskQueue] 锁已获取");

    if (task_queue_.empty()) {
        task_running_ = false;
        ESP_LOGI(TAG, "📋 [TaskQueue] 队列为空，停止");
        return;
    }

    task_running_ = true;
    TaskItem task = task_queue_.front();
    task_queue_.pop();
    ESP_LOGI(TAG, "📋 [TaskQueue] 取出任务: %s, 剩余: %d",
             task.type.c_str(), (int)task_queue_.size());

    lock.unlock();
    ESP_LOGI(TAG, "📋 [TaskQueue] 锁已释放");
    ExecuteTask(task);
}

void Application::ExecuteTask(const TaskItem& task) {
    ESP_LOGI(TAG, "⚡ [Task] 执行: %s", task.type.c_str());

    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();

    if (task.type == "tts") {
        // TTS 播报（直接播放，绕过状态机）
        PlayTtsDirectly(task.text);
        // TTS 播放完成后，通过定时器触发下一个任务
        StartTaskTimer();

    } else if (task.type == "gpio") {
        if (task.gpio_pin >= 0) {
            if (!EnsureOutput(task.gpio_pin)) {
                ESP_LOGW(TAG, "  GPIO %d 配置为输出失败", task.gpio_pin);
            }
            gpio_set_level((gpio_num_t)task.gpio_pin, task.gpio_level);
            ESP_LOGI(TAG, "  GPIO %d -> %d (hold %d ms)", task.gpio_pin, task.gpio_level,
                     task.duration_ms);
            if (task.duration_ms > 0) {
                /* 到点回落到低电平（"高电平 N 秒"就是这个语义）。
                 * 用现成的延时通道推进队列，和 move 的收尾方式一致。 */
                TaskItem revert;
                revert.type = "gpio";
                revert.gpio_pin = task.gpio_pin;
                revert.gpio_level = 0;
                revert.duration_ms = 0;
                AppendTask(revert);
                ProcessNextTaskAfterDelay(task.duration_ms);
                return;
            }
        }
        // GPIO 立即完成，继续下一个
        ProcessNextTask();

    } else if (task.type == "pwm") {
        if (task.pwm_pin >= 0) {
            ApplyPinPwm(task.pwm_pin, (uint32_t)task.pwm_freq_hz, task.pwm_pulse_us,
                        task.pwm_duty_pct, task.pwm_use_duty);
            if (task.duration_ms > 0) {
                /* 到点收手：同一个引脚再来一条空 PWM（占空比 0）。
                 * 舵机脉冲消失即松劲，电机占空比归零即停。 */
                TaskItem stop;
                stop.type = "pwm";
                stop.pwm_pin = task.pwm_pin;
                stop.pwm_freq_hz = task.pwm_freq_hz;
                stop.pwm_use_duty = true;
                stop.pwm_duty_pct = 0;
                stop.duration_ms = 0;
                AppendTask(stop);
                ProcessNextTaskAfterDelay(task.duration_ms);
                return;
            }
        }
        ProcessNextTask();

    } else if (task.type == "servo") {
        board.SetServoAngle(task.servo_angle);
        ESP_LOGI(TAG, "  Servo -> %d°", task.servo_angle);
        ProcessNextTask();

    } else if (task.type == "move") {
        if (task.move_dir == "forward") board.MoveForward();
        else if (task.move_dir == "backward") board.MoveBackward();
        else if (task.move_dir == "left") board.TurnLeft();
        else if (task.move_dir == "right") board.TurnRight();
        else if (task.move_dir == "stop") board.Stop();
        ESP_LOGI(TAG, "  Move: %s, duration: %d ms", task.move_dir.c_str(), task.duration_ms);

        if (task.duration_ms > 0 && task.move_dir != "stop") {
            // 移动需要延时后自动停止
            StartTaskTimer();
            // 保存当前任务类型，以便定时器回调时停止移动
            // 这里简化处理：用延时任务代替
            TaskItem delay_task;
            delay_task.type = "delay";
            delay_task.duration_ms = task.duration_ms;
            // 在延时后追加一个 stop 动作
            TaskItem stop_task;
            stop_task.type = "move";
            stop_task.move_dir = "stop";
            AppendTask(stop_task);
            // 延时结束后继续
            ProcessNextTaskAfterDelay(task.duration_ms);
        } else {
            ProcessNextTask();
        }

    } else if (task.type == "camera") {
        auto camera = board.GetCamera();
        if (camera == nullptr) {
            ESP_LOGW(TAG, "  [CAMERA] 这块板没有摄像头");
        } else {
            ESP_LOGI(TAG, "  [CAMERA] 抓帧开始 (op=%s)", task.cam_op.c_str());
            if (!camera->Capture()) {
                ESP_LOGE(TAG, "  [CAMERA] 抓帧失败");
            } else {
                ESP_LOGI(TAG, "  [CAMERA] 抓帧成功");
                if (task.cam_op == "explain") {
                    // Explain 需要后台下发过 vision url（MCP initialize 里给的）
                    try {
                        std::string result = camera->Explain("请描述这张图片");
                        ESP_LOGI(TAG, "  [CAMERA] explain 返回: %s", result.c_str());
                    } catch (const std::exception& e) {
                        ESP_LOGW(TAG, "  [CAMERA] explain 失败: %s", e.what());
                    }
                }
            }
        }
        ProcessNextTask();

    } else if (task.type == "ws2812") {
        if (task.ws_pin >= 0) {
            ApplyWs2812(task.ws_pin, task.ws_count, task.ws_r, task.ws_g, task.ws_b);
            if (task.duration_ms > 0) {
                /* 到点关灯：队列尾部追加一条"清零"任务，和 gpio 的收尾方式一致 */
                TaskItem off;
                off.type = "ws2812";
                off.ws_pin = task.ws_pin;
                off.ws_count = task.ws_count;
                off.ws_r = 0;
                off.ws_g = 0;
                off.ws_b = 0;
                off.duration_ms = 0;
                AppendTask(off);
                ProcessNextTaskAfterDelay(task.duration_ms);
                return;
            }
        }
        ProcessNextTask();

    } else if (task.type == "stepper") {
        /* 步进电机：交给板级驱动（非阻塞），然后按估算的走完时间恢复队列。
         *
         * 为什么用"估算时间 + 延时"而不是在这里轮询 motor_is_running()：
         * 这里跑在主事件循环里，阻塞 2 秒会把音频收发和状态机一起卡住
         * （台账 2026-10-19 踩过：忙等导致调用者日志延后、音频卡顿）。
         * 估算 = steps / speed_hz 秒，多给 120ms 余量。
         */
        int steps = task.st_steps;
        if (task.st_motor < 0 || task.st_motor > 1 || steps == 0) {
            ESP_LOGW(TAG, "  [STEPPER] 参数无效 motor=%d steps=%d", task.st_motor, steps);
            ProcessNextTask();
        } else {
            if (steps > 1024) steps = 1024;
            if (steps < -1024) steps = -1024;

            int speed = task.st_speed_hz > 0 ? task.st_speed_hz : 60;
            if (speed > 400) speed = 400;      // 太快会丢步

            ESP_LOGI(TAG, "  [STEPPER] motor=%d steps=%d(%s) speed=%d release=%d",
                     task.st_motor, steps, steps > 0 ? "CW" : "CCW", speed,
                     task.st_hold ? 0 : 1);

            board.StepMotor(task.st_motor, steps, speed, task.st_hold);

            int abs_steps = steps > 0 ? steps : -steps;
            int est_ms = (int)((int64_t)abs_steps * 1000 / speed) + 120;
            ProcessNextTaskAfterDelay(est_ms);
        }

    } else if (task.type == "delay") {
        ESP_LOGI(TAG, "  Delay: %d ms", task.duration_ms);
        if (task.duration_ms > 0) {
            StartTaskTimer();
        } else {
            ProcessNextTask();
        }

    } else if (task.type == "emotion") {
        display->SetEmotion(task.emotion.c_str());
        ESP_LOGI(TAG, "  Emotion: %s", task.emotion.c_str());
        ProcessNextTask();

    } else {
        ESP_LOGW(TAG, " 未知任务类型: %s", task.type.c_str());
        ProcessNextTask();
    }
}

void Application::StartTaskTimer() {
    if (task_timer_handle_) {
        // 如果有定时器在运行，先停止
        esp_timer_stop(task_timer_handle_);
    }
    // 启动定时器，100ms 后触发，用于轮询检查
    esp_timer_start_once(task_timer_handle_, 100 * 1000);
}

void Application::StopTaskTimer() {
    if (task_timer_handle_) {
        esp_timer_stop(task_timer_handle_);
    }
}

void Application::TaskTimerCallback(void* arg) {
    Application* app = static_cast<Application*>(arg);
    // 在定时器回调中，我们简单检查 TTS 是否播放完成
    // 由于 TTS 播放是异步的，需要检查 audio_service 是否空闲
    if (app->audio_service_.IsIdle()) {
        // 音频播完了，处理下一个任务
        app->ProcessNextTask();
    } else {
        // 还没播完，继续等待
        app->StartTaskTimer();
    }
}

// 辅助函数：延时后继续处理
void Application::ProcessNextTaskAfterDelay(int delay_ms) {
    ESP_LOGI(TAG, "⏰ [Delay] 延时 %d ms 后继续", delay_ms);
    if (task_timer_handle_) {
        esp_timer_stop(task_timer_handle_);
        esp_timer_start_once(task_timer_handle_, delay_ms * 1000);
    } else {
        // 后备方案：直接延时（会阻塞，但保证能继续）
        vTaskDelay(pdMS_TO_TICKS(delay_ms));
        ProcessNextTask();
    }
}