#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目统计工具 - GUI版本
使用wxPython实现图形界面，支持目录选择、实时统计、结果复制
支持所有文件类型，自动识别文本/二进制
"""

import os
import wx
import wx.lib.newevent
from pathlib import Path
from datetime import datetime
from threading import Thread
import queue

# 要排除的目录
EXCLUDE_DIRS = {
    '__pycache__', '.git', '.idea', '.vscode', 'venv', 'env',
    'node_modules', 'dist', 'browser_profiles', 'logs', 'storage', 'reports'
}

# 定义更新事件
UpdateEvent, EVT_UPDATE = wx.lib.newevent.NewEvent()
FinishEvent, EVT_FINISH = wx.lib.newevent.NewEvent()


def get_file_icon(file_path, is_binary=False):
    """根据文件类型返回合适的图标"""
    ext = os.path.splitext(file_path)[1].lower()

    # 代码/脚本文件
    if ext in {'.py', '.pyw'}:
        return '🐍'
    elif ext in {'.c', '.cpp', '.cc', '.cxx'}:
        return '⚙️'
    elif ext in {'.h', '.hpp', '.hh'}:
        return '🔧'
    elif ext in {'.js', '.mjs', '.cjs'}:
        return '💛'
    elif ext in {'.html', '.htm'}:
        return '🌐'
    elif ext in {'.css', '.scss', '.sass'}:
        return '🎨'
    elif ext in {'.json', '.jsonc'}:
        return '📋'
    elif ext in {'.md', '.markdown'}:
        return '📝'
    elif ext in {'.sql'}:
        return '🗄️'
    elif ext in {'.txt', '.log', '.ini', '.cfg', '.conf'}:
        return '📄'
    elif ext in {'.xml', '.xsd', '.xsl'}:
        return '📰'
    elif ext in {'.yml', '.yaml'}:
        return '📋'
    elif ext in {'.sh', '.bash', '.zsh'}:
        return '🐚'
    elif ext in {'.bat', '.cmd', '.ps1'}:
        return '💻'
    elif ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico'}:
        return '🖼️'
    elif ext in {'.mp3', '.wav', '.flac', '.ogg'}:
        return '🎵'
    elif ext in {'.mp4', '.avi', '.mov', '.mkv'}:
        return '🎬'
    elif ext in {'.zip', '.tar', '.gz', '.bz2', '.7z', '.rar'}:
        return '📦'
    elif ext in {'.exe', '.msi', '.dll', '.so', '.dylib'}:
        return '⚡'
    elif ext in {'.bin', '.rom', '.hex'}:
        return '🔢'
    elif ext in {'.pdf'}:
        return '📕'
    elif ext in {'.doc', '.docx'}:
        return '📘'
    elif ext in {'.xls', '.xlsx'}:
        return '📗'
    elif ext in {'.ppt', '.pptx'}:
        return '📙'
    else:
        return '🔹' if is_binary else '📄'


def is_text_file(file_path, sample_size=8192):
    """判断文件是否为文本文件（读取前N字节，检查是否包含二进制数据）"""
    try:
        with open(file_path, 'rb') as f:
            sample = f.read(sample_size)

        # 检查空文件
        if not sample:
            return True

        # 检查是否包含空字节（二进制文件的典型特征）
        if b'\x00' in sample:
            return False

        # 尝试解码为UTF-8
        try:
            sample.decode('utf-8')
            return True
        except UnicodeDecodeError:
            # 尝试其他常见编码
            try:
                sample.decode('gbk')
                return True
            except UnicodeDecodeError:
                return False
    except Exception:
        return False


def read_text_file(file_path):
    """读取文本文件内容，自动尝试多种编码"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
                lines = content.count('\n') + 1
                chars = len(content)
                return lines, chars, content
        except (UnicodeDecodeError, UnicodeError):
            continue

    # 所有编码都失败，降级为二进制统计
    return 0, 0, None


def count_file(file_path):
    """统计单个文件，自动判断文本/二进制"""
    try:
        file_size = os.path.getsize(file_path)

        # 判断是否为文本文件
        if is_text_file(file_path):
            lines, chars, _ = read_text_file(file_path)
            return {
                'type': 'text',
                'lines': lines,
                'chars': chars,
                'size': file_size,
                'size_display': format_size(file_size)
            }
        else:
            # 二进制文件，只显示大小
            return {
                'type': 'binary',
                'lines': 0,
                'chars': 0,
                'size': file_size,
                'size_display': format_size(file_size)
            }
    except Exception as e:
        return {
            'type': 'error',
            'lines': 0,
            'chars': 0,
            'size': 0,
            'size_display': '读取失败',
            'error': str(e)
        }


def format_size(size_bytes):
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class FileStats:
    """文件统计信息"""

    def __init__(self):
        self.total_files = 0
        self.total_lines = 0
        self.total_chars = 0
        self.total_size = 0
        self.type_stats = {}
        self.tree_data = []


class WorkerThread(Thread):
    """后台统计线程"""

    def __init__(self, root_path, update_queue):
        super().__init__()
        self.root_path = root_path
        self.update_queue = update_queue
        self.daemon = True

    def run(self):
        stats = FileStats()
        self.scan_directory(stats, self.root_path, 0)
        self.update_queue.put(('finish', stats))

    def scan_directory(self, stats, root_path, level, prefix="", is_last=True):
        """递归扫描目录"""
        if level > 15:
            return

        dir_name = os.path.basename(root_path)
        if not dir_name:
            dir_name = root_path

        # 构建树形结构字符串
        if level == 0:
            tree_line = f"📁 {dir_name}/\n"
        else:
            connector = "└── " if is_last else "├── "
            tree_line = f"{prefix}{connector}📁 {dir_name}/\n"

        self.update_queue.put(('tree', tree_line))

        # 更新前缀
        new_prefix = prefix + ("    " if is_last else "│   ")

        try:
            items = sorted(os.listdir(root_path))
        except PermissionError:
            self.update_queue.put(('tree', f"{new_prefix}    ⚠️ 无权限访问\n"))
            return
        except Exception:
            return

        # 分离文件和目录
        files = []
        dirs = []
        for item in items:
            if item in EXCLUDE_DIRS:
                continue
            item_path = os.path.join(root_path, item)
            if os.path.isdir(item_path):
                dirs.append(item)
            else:
                files.append(item)

        files.sort()
        dirs.sort()

        # 处理文件
        for i, file in enumerate(files):
            is_last_file = (i == len(files) - 1) and not dirs
            file_path = os.path.join(root_path, file)

            # 统计文件
            file_info = count_file(file_path)

            # 更新统计
            stats.total_files += 1
            if file_info['type'] == 'text':
                stats.total_lines += file_info['lines']
                stats.total_chars += file_info['chars']
            stats.total_size += file_info['size']

            # 获取扩展名用于分类统计
            ext = os.path.splitext(file)[1].lower()
            if not ext:
                ext = '(无扩展名)'

            # 更新类型统计
            if ext not in stats.type_stats:
                stats.type_stats[ext] = {
                    'files': 0, 'lines': 0, 'chars': 0, 'size': 0,
                    'binary_count': 0, 'text_count': 0
                }
            stats.type_stats[ext]['files'] += 1
            if file_info['type'] == 'text':
                stats.type_stats[ext]['lines'] += file_info['lines']
                stats.type_stats[ext]['chars'] += file_info['chars']
                stats.type_stats[ext]['text_count'] += 1
            else:
                stats.type_stats[ext]['binary_count'] += 1
            stats.type_stats[ext]['size'] += file_info['size']

            # 生成显示行
            icon = get_file_icon(file_path, file_info['type'] == 'binary')
            connector = "└── " if is_last_file else "├── "

            if file_info['type'] == 'text':
                file_line = f"{new_prefix}{connector}{icon} {file} ({file_info['lines']:,} 行, {file_info['chars']:,} 字, {file_info['size_display']})\n"
            else:
                file_line = f"{new_prefix}{connector}{icon} {file} [二进制] ({file_info['size_display']})\n"

            self.update_queue.put(('tree', file_line))

        # 处理子目录
        for i, dir_name in enumerate(dirs):
            is_last_dir = (i == len(dirs) - 1)
            dir_path = os.path.join(root_path, dir_name)
            self.scan_directory(stats, dir_path, level + 1, new_prefix, is_last_dir)


class MainFrame(wx.Frame):
    """主窗口"""

    def __init__(self):
        super().__init__(None, title="项目统计工具 - 支持所有文件类型", size=(1000, 750))

        self.current_path = None
        self.stats = None
        self.update_queue = queue.Queue()
        self.worker = None

        self.init_ui()
        self.set_icons()
        self.bind_events()

        # 定时器处理队列消息
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.process_queue, self.timer)
        self.timer.Start(100)

        self.Centre()

    def init_ui(self):
        """初始化UI"""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 顶部：目录选择区域
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.dir_text = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.dir_text.SetMinSize((500, -1))
        top_sizer.Add(self.dir_text, 1, wx.ALL | wx.EXPAND, 5)

        self.browse_btn = wx.Button(panel, label="📁 选择目录", size=(120, -1))
        top_sizer.Add(self.browse_btn, 0, wx.ALL, 5)

        self.start_btn = wx.Button(panel, label="▶ 开始统计", size=(120, -1))
        self.start_btn.Enable(False)
        top_sizer.Add(self.start_btn, 0, wx.ALL, 5)

        main_sizer.Add(top_sizer, 0, wx.EXPAND)

        # 分割线
        line = wx.StaticLine(panel, style=wx.LI_HORIZONTAL)
        main_sizer.Add(line, 0, wx.EXPAND | wx.ALL, 5)

        # 统计结果显示区域
        splitter = wx.SplitterWindow(panel, style=wx.SP_3D)

        # 左侧：目录树显示
        left_panel = wx.Panel(splitter, style=wx.BORDER_SUNKEN)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        left_label = wx.StaticText(left_panel, label="📂 目录结构 (绿色=文本文件, 蓝色=二进制)")
        left_label.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        left_sizer.Add(left_label, 0, wx.ALL, 5)

        self.tree_text = wx.TextCtrl(left_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.tree_text.SetFont(wx.Font(9, wx.MODERN, wx.NORMAL, wx.NORMAL))
        left_sizer.Add(self.tree_text, 1, wx.ALL | wx.EXPAND, 5)

        left_panel.SetSizer(left_sizer)

        # 右侧：统计信息
        right_panel = wx.Panel(splitter, style=wx.BORDER_SUNKEN)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        right_label = wx.StaticText(right_panel, label="📊 统计信息")
        right_label.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        right_sizer.Add(right_label, 0, wx.ALL, 5)

        self.stats_text = wx.TextCtrl(right_panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.stats_text.SetFont(wx.Font(9, wx.MODERN, wx.NORMAL, wx.NORMAL))
        right_sizer.Add(self.stats_text, 1, wx.ALL | wx.EXPAND, 5)

        right_panel.SetSizer(right_sizer)

        splitter.SplitVertically(left_panel, right_panel, 550)
        main_sizer.Add(splitter, 1, wx.ALL | wx.EXPAND, 5)

        # 底部：按钮区域
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.progress_bar = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL)
        self.progress_bar.SetValue(0)
        bottom_sizer.Add(self.progress_bar, 1, wx.ALL | wx.EXPAND, 5)

        self.status_text = wx.StaticText(panel, label="就绪")
        bottom_sizer.Add(self.status_text, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        self.copy_btn = wx.Button(panel, label="📋 复制全部", size=(100, -1))
        self.copy_btn.Enable(False)
        bottom_sizer.Add(self.copy_btn, 0, wx.ALL, 5)

        self.clear_btn = wx.Button(panel, label="🗑 清空", size=(80, -1))
        bottom_sizer.Add(self.clear_btn, 0, wx.ALL, 5)

        main_sizer.Add(bottom_sizer, 0, wx.EXPAND)

        panel.SetSizer(main_sizer)

    def set_icons(self):
        """设置图标（可选）"""
        pass

    def bind_events(self):
        """绑定事件"""
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start)
        self.copy_btn.Bind(wx.EVT_BUTTON, self.on_copy)
        self.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)

    def on_browse(self, event):
        """选择目录"""
        dialog = wx.DirDialog(self, "选择要统计的项目目录", style=wx.DD_DEFAULT_STYLE)
        if dialog.ShowModal() == wx.ID_OK:
            self.current_path = dialog.GetPath()
            self.dir_text.SetValue(self.current_path)
            self.start_btn.Enable(True)
            self.status_text.SetLabel("已选择目录，点击开始统计")
        dialog.Destroy()

    def on_start(self, event):
        """开始统计"""
        if not self.current_path:
            wx.MessageBox("请先选择目录", "提示", wx.OK | wx.ICON_WARNING)
            return

        # 清空现有内容
        self.tree_text.Clear()
        self.stats_text.Clear()
        self.progress_bar.SetValue(0)
        self.copy_btn.Enable(False)

        # 清空队列
        while not self.update_queue.empty():
            try:
                self.update_queue.get_nowait()
            except queue.Empty:
                break

        # 开始统计
        self.status_text.SetLabel("正在统计...")
        self.start_btn.Enable(False)
        self.browse_btn.Enable(False)

        self.worker = WorkerThread(self.current_path, self.update_queue)
        self.worker.start()

    def process_queue(self, event):
        """处理队列消息"""
        if self.update_queue.empty():
            return

        try:
            while True:
                msg = self.update_queue.get_nowait()
                if msg[0] == 'tree':
                    # 添加树形结构行
                    self.tree_text.AppendText(msg[1])
                    self.tree_text.ShowPosition(self.tree_text.GetLastPosition())
                elif msg[0] == 'finish':
                    self.on_finish(msg[1])
                    break
        except queue.Empty:
            pass

    def on_finish(self, stats):
        """统计完成"""
        self.stats = stats

        # 生成统计报告
        report = self.generate_report(stats)
        self.stats_text.SetValue(report)

        # 更新状态
        total_binary = sum(1 for ext, s in stats.type_stats.items() if s['binary_count'] > 0)
        self.status_text.SetLabel(
            f"统计完成！共 {stats.total_files:,} 个文件，"
            f"{stats.total_lines:,} 行代码，"
            f"总大小 {format_size(stats.total_size)}"
        )
        self.progress_bar.SetValue(100)
        self.start_btn.Enable(True)
        self.browse_btn.Enable(True)
        self.copy_btn.Enable(True)

        wx.Bell()

    def generate_report(self, stats):
        """生成统计报告"""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("项目统计报告")
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"项目路径: {self.current_path}")
        report_lines.append("=" * 80)
        report_lines.append("")

        report_lines.append("📈 总体统计:")
        report_lines.append(f"   ├── 总文件数: {stats.total_files:,}")
        report_lines.append(f"   ├── 文本文件行数: {stats.total_lines:,}")
        report_lines.append(f"   ├── 文本文件字符数: {stats.total_chars:,}")
        report_lines.append(f"   └── 总文件大小: {format_size(stats.total_size)}")
        report_lines.append("")

        report_lines.append("📁 按文件类型统计:")
        report_lines.append(f"   {'扩展名':<15} {'文件数':>8} {'行数':>12} {'字符数':>12} {'大小':>12}")
        report_lines.append(f"   {'-' * 15} {'-' * 8} {'-' * 12} {'-' * 12} {'-' * 12}")

        for ext, type_stats in sorted(stats.type_stats.items(), key=lambda x: x[1]['files'], reverse=True):
            ext_display = ext[:14] if len(ext) < 15 else ext[:12] + ".."
            binary_mark = f" ({type_stats['binary_count']}个二进制)" if type_stats['binary_count'] > 0 else ""
            report_lines.append(
                f"   {ext_display:<15} {type_stats['files']:>8,}"
                f"{type_stats['lines']:>12,} {type_stats['chars']:>12,} "
                f"{format_size(type_stats['size']):>12}{binary_mark}"
            )
        report_lines.append("")

        # 添加说明
        report_lines.append("📌 说明:")
        report_lines.append("   • 文本文件: 统计行数、字符数")
        report_lines.append("   • 二进制文件: 只统计文件大小，不统计行数/字符数")
        report_lines.append("")
        report_lines.append("=" * 80)

        return "\n".join(report_lines)

    def on_copy(self, event):
        """复制全部内容到剪贴板"""
        if not self.stats:
            wx.MessageBox("没有可复制的数据", "提示", wx.OK | wx.ICON_WARNING)
            return

        # 组合所有内容
        content = []
        content.append("=" * 80)
        content.append(f"项目路径: {self.current_path}")
        content.append("=" * 80)
        content.append("")
        content.append("【目录结构】")
        content.append(self.tree_text.GetValue())
        content.append("")
        content.append("【统计信息】")
        content.append(self.stats_text.GetValue())

        full_content = "\n".join(content)

        # 复制到剪贴板
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(full_content))
            wx.TheClipboard.Close()
            wx.MessageBox("已复制到剪贴板！", "成功", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("无法打开剪贴板", "错误", wx.OK | wx.ICON_ERROR)

    def on_clear(self, event):
        """清空所有内容"""
        if wx.MessageBox("确定要清空所有内容吗？", "确认",
                         wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
            self.tree_text.Clear()
            self.stats_text.Clear()
            self.stats = None
            self.copy_btn.Enable(False)
            self.progress_bar.SetValue(0)
            self.status_text.SetLabel("已清空")
            if self.current_path:
                self.start_btn.Enable(True)


class ProjectStatsApp(wx.App):
    """应用程序类"""

    def OnInit(self):
        self.frame = MainFrame()
        self.frame.Show()
        return True


def main():
    """主函数"""
    app = ProjectStatsApp(False)
    app.MainLoop()


if __name__ == "__main__":
    main()