from bubble.uiml import register_parser
import uiml

register_parser()  # Register the parser

uiml_file = """
    <layout direction='v' stretch=true>
        <bubble::toggleSwitch signals={'stateChanged': lambda state: print('toggleSwitch state changed', state)} />
        <QLabel args=['hello!'] />
    </layout>
"""

if __name__ == '__main__':
    app = uiml.QApplication([])
    window = uiml.QWidget()

    # QLineEdit / QComboBox 通过 additional 提供给 XML 标签解析
    data = uiml.compile_ui(
        uiml.xml_parse(uiml_file),
    )
    layout = uiml.UIMLLayout(data).show()
    window.setLayout(layout)

    window.show()
    app.exec()