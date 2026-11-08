# ==== DEMO ====
from bubble.QUI import *
from bubble.navigate import *

#: Demo 用的 QSS：数值与 THEME_DEFAULTS / 当前常量保持一致，可在这里改主题。
DEMO_QSS = """
NavigationView {
    qproperty-selectedBg: #2d2d2d;
    qproperty-selectedHoverBg: #292929;
    qproperty-selectedPressedBg: #2d2d2d;
    qproperty-hoverBg: #2d2d2d;
    qproperty-pressedBg: #292929;
    qproperty-textColor: #ffffff;
    qproperty-pressedText: #cfcfcf;
    qproperty-separatorColor: #cccccc;
    qproperty-dividerColor: #313131;
    qproperty-indicatorColor: #99ebff;
    qproperty-indicatorWidth: 2;
    qproperty-indicatorHeight: 16;
    qproperty-navItemRadius: 4;
    qproperty-flyoutRadius: 8;
    qproperty-flyoutItemRadius: 4;
}

HighLightPanel {
    qproperty-cornerRadius: 8;
}

HoverToolTip {
    qproperty-tipBgColor: #2d2d2d;
    qproperty-tipTextColor: #ffffff;
    qproperty-tipRadius: 8;
    qproperty-tipPadding: 12;
    qproperty-tipFontSize: 14;
    qproperty-tipDelayMs: 1000;
    qproperty-tipFadeMs: 250;
    qproperty-tipOffsetX: 0;
    qproperty-tipOffsetY: -20;
}

QToolTip {
    background-color: #2d2d2d;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    padding: 4px 8px;
}

_CapsuleScrollBar {
    qproperty-barColor: #9f9f9f;
}
"""


def _page(title: str, text: str) -> QVBoxLayout:
    """Demo 用的简单页面布局。"""
    box = QVBoxLayout()
    head = QLabel(title)
    head.setStyleSheet("font-size: 22px; font-weight: 600; color: #ffffff;")
    body = QLabel(text)
    body.setWordWrap(True)
    body.setStyleSheet("color: #bdbdbd; font-size: 14px;")
    box.addWidget(head)
    box.addWidget(body)
    box.addStretch(1)
    return box


def _demo_icon() -> QIcon:
    """画一个简单的 16x16 应用图标（蓝色圆角方块 + 白色窗口图案）。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        gradient = QLinearGradient(0, 0, 64, 64)
        gradient.setColorAt(0.0, QColor("#4CC2FF"))
        gradient.setColorAt(1.0, QColor("#0067C0"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)

        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawRoundedRect(QRectF(16, 16, 32, 32), 5, 5)
        painter.setBrush(QColor("#0067C0"))
        painter.drawRoundedRect(QRectF(21, 21, 22, 7), 2, 2)
    finally:
        painter.end()
    return QIcon(pixmap)


def _demo_body_stylesheet() -> str:
    fg, muted, panel =  "#F5F5F5", "#A0A0A0", "#242424"
    return f"""
QLabel#DemoHeading {{
    color: {fg};
    font-size: 26px;
    font-family: "Segoe UI Variable Display", "Segoe UI";
}}
QLabel#DemoText {{
    color: {muted};
    font-size: 13px;
    font-family: "Segoe UI Variable Text", "Segoe UI";
}}
QTextEdit#DemoTextEdit {{
    background-color: {panel};
    color: {fg};
    border: 1px solid {"#3A3A3A"};
    border-radius: 8px;
    padding: 8px;
    font-size: 13px;
    font-family: "Segoe UI Variable Text", "Segoe UI";
}}
QPushButton {{
    background-color: {panel};
    color: {fg};
    border: 1px solid {"#3A3A3A"};
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13px;
    font-family: "Segoe UI Variable Text", "Segoe UI";
}}
QPushButton:hover {{
    background-color: {"#2E2E2E"};
}}
QPushButton:pressed {{
    background-color: {"#3A3A3A"};
}}
"""

class DemoWindow(TitleBarWindow):
    """自定义标题栏 + 内容区侧边栏：主页展示标题栏示例内容。"""

    #: 演示里循环切换的标题栏高度（逻辑像素）
    _DEMO_HEIGHTS = (32, 40, 48, 56)

    def __init__(self):
        # 深色内容配色；标题栏保留玻璃透明背景。
        super().__init__(title="自定义标题栏 · NavigationView 示例",
                         icon=_demo_icon(), dark=True, auto_theme=False)
        self.setMinimumSize(900, 600)
        self.resize(1180, 760)
        self._init_navigation()

    # ------------------------------------------------------------------
    # 导航（内容区侧边栏）
    # ------------------------------------------------------------------
    def _init_navigation(self) -> None:
        self._nav = NavigationView()
        # initNavigationView 会自动把 nav 加入 body_layout，并把返回/汉堡
        # 按钮迁移到 TitleBar；同时启用内容卡片的深色底与左上圆角。
        self.title_bar.initNavigationView(self._nav, move_animate_button=True)
        # 标题栏使用和侧边栏一样的玻璃：共用 NavigationView 的采样源，
        # 材质（SIDEBAR_GLASS）也一致（保留透明/玻璃背景）。

        self.title_bar.setSubTitle("Dev · 深色")
        self._nav.setAutoHideBack(True)

        self._nav.addNavItem("\uE80F", "主页", self._home_layout())
        self._nav.addNavItem("", "文档", _page("文档", "这里是文档内容。"))
        self._nav.addSeparator("资源")

        dev = self._nav.addNavFoldItem("\uE713", "开发")
        dev.addNavItem("\uE774", "网络", _page("网络", "网络相关设置。"))
        dev.addNavItem("\uE703", "蓝牙", _page("蓝牙", "蓝牙相关设置。"))

        self._nav.addSeparateLine()

        help_item = self._nav.addNavFoldItem(
            "\uE897", "帮助", _page("帮助", "帮助与反馈。"))
        help_item.addNavItem("\uE939", "反馈", _page("反馈", "反馈与建议。"))
        help_item.addNavItem("\uE946", "关于", _page("关于", "NavigationView 示例。"))
        self._nav.setSettingLayout(_page("设置", "应用设置。"))
        self._nav.setSelectedNavItem(0)

    # ------------------------------------------------------------------
    # 主页：标题栏示例内容
    # ------------------------------------------------------------------
    def _home_layout(self) -> QVBoxLayout:
        page = QVBoxLayout()
        page.setContentsMargins(0, 0, 0, 0)

        body = QWidget()
        body.setObjectName("DemoBody")
        body.setStyleSheet(_demo_body_stylesheet())
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        heading = QLabel("PySide6 自定义标题栏")
        heading.setObjectName("DemoHeading")
        layout.addWidget(heading)

        description = QLabel(
            "原生窗口效果全部保留：\n"
            "· 窗口阴影 / Windows 11 圆角\n"
            "· 最小化、最大化、还原的 DWM 动画\n"
            "· 拖动标题栏移动窗口，双击最大化/还原\n"
            "· 左键图标 / 右键标题栏 / Alt+Space 弹出系统菜单\n"
            "· 双击应用图标可直接关闭窗口\n"
            "· Aero Snap / Win+方向键贴靠\n"
            "· 鼠标悬停最大化按钮出现 Windows 11 贴靠布局\n"
            "· 标题栏高度可配置（height=…，按钮命中区域同步）")
        description.setObjectName("DemoText")
        description.setWordWrap(True)
        layout.addWidget(description)

        self._text_edit = QTextEdit(body)
        self._text_edit.setObjectName("DemoTextEdit")
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlainText(
            "标题栏的按钮走 Windows 原生非客户区命中测试：\n"
            "    WM_NCHITTEST -> HTMINBUTTON / HTMAXBUTTON / HTCLOSE\n"
            "悬停时系统会自动提供 Windows 11 贴靠布局；\n"
            "点击由组件自己 SetCapture + WM_SYSCOMMAND 触发，\n"
            "既保证最小化/最大化可靠，也避免 DefWindowProc 把标准\n"
            "标题栏按钮画进客户区（按下时按钮旁边出现白底按钮）。\n\n"
            "窗口本身保留了 WS_OVERLAPPEDWINDOW 样式，DWM 因此会提供\n"
            "阴影、圆角、最小化/最大化动画、任务栏预览与 Aero Snap。\n\n"
            "标题栏高度在构造时用 height=40 指定；运行时调用\n"
            "set_title_bar_height() 也会同步按钮尺寸与命中测试区域。\n\n"
            "系统菜单由 Qt 自绘（圆角/阴影/渐显），支持还原、移动、大小、\n"
            "最小化、最大化、关闭；移动/大小会进入对应的光标提示模式。")
        layout.addWidget(self._text_edit, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        minimize_btn = QPushButton("最小化")
        minimize_btn.clicked.connect(self.showMinimized)
        maximize_btn = QPushButton("最大化 / 还原")
        maximize_btn.clicked.connect(
            lambda: self.showNormal() if self.isMaximized() else self.showMaximized())
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        self._height_btn = QPushButton(f"标题栏高度：{self.title_bar_height()}")
        self._height_btn.clicked.connect(self._cycle_title_bar_height)
        for button in (minimize_btn, maximize_btn, close_btn, self._height_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._status = QLabel("")
        self._status.setObjectName("DemoText")
        layout.addWidget(self._status)
        self._update_status()

        page.addWidget(body, 1)
        return page

    # ------------------------------------------------------------------
    # 标题栏高度 / 状态
    # ------------------------------------------------------------------
    def _cycle_title_bar_height(self):
        """演示运行时改高度：按钮/命中区域会一起变。"""
        heights = self._DEMO_HEIGHTS
        try:
            index = heights.index(self.title_bar_height())
        except ValueError:
            index = 0
        height = heights[(index + 1) % len(heights)]
        self.set_title_bar_height(height)
        if hasattr(self, "_height_btn"):
            self._height_btn.setText(f"标题栏高度：{height}")

    def _update_status(self):
        state = "最大化" if self.isMaximized() else "窗口化"
        self._status.setText(
            f"窗口状态：{state}　标题栏高度：{self.title_bar_height()}　"
            "（拖动标题栏 / 双击标题栏试试）")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "_status"):
            self._update_status()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Custom Titlebar + NavigationView")
    app.setStyleSheet(DEMO_QSS)
    window = DemoWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
