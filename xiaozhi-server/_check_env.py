# 环境检查：把"装了没有"和"装的是哪个版本"一次说清
import importlib
import importlib.metadata as md

# 导入名 -> 发行包名（不同名的手工列，否则会误判成"没装"）
DIST = {
    "yaml": "PyYAML",
    "silero_vad": "silero_vad",
    "ruamel.yaml": "ruamel.yaml",
    "edge_tts": "edge_tts",
    "opuslib": "opuslib_next",
    "torch": "torch",
    "torchaudio": "torchaudio",
}

mods = [
    "yaml", "aioconsole", "aiohttp", "websockets", "loguru", "openai",
    "torch", "torchaudio", "funasr", "edge_tts", "numpy", "silero_vad",
    "ruamel.yaml", "httpx", "pydub", "mcp", "psutil", "dashscope",
    "modelscope", "opuslib",
]

ok, bad = [], []
for name in mods:
    try:
        importlib.import_module(name)
    except Exception as e:
        bad.append("%s (%s)" % (name, type(e).__name__))
        continue
    dist = DIST.get(name, name)
    try:
        ver = md.version(dist)
    except Exception:
        ver = "?"
    ok.append("%s==%s" % (name, ver))

print("=== 已装 (%d) ===" % len(ok))
for i in ok:
    print("  " + i)
print("=== 缺失 (%d) ===" % len(bad))
for i in bad:
    print("  " + i)
