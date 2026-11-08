'''
本项目对 uiml 的扩展（新版 Parser API）。

调用 register_parser() 即可一键注册值替换器、组件解析器、布局解析器、
自定义渲染类 uiml.UIMLLayout 以及需要自动读取的字段；
不需要再调用 uiml.enable_namespace_api() / uiml.set_namespace()。
'''
import uiml
from .i18n import get_lang

from .widgets import ToggleSwitch, UnitInputLayout
from .cards import Expander, PressableRow, create_expander_row, Card, ContentCard
from .icon import FontIcon # 这些都是我这个项目中的函数，别管

from typing import Any

__all__ = [
    'register_parser', 'widget_replacer', 'widget_parser', 'layout_parser',
    'uiml.UIMLLayout', 'BubbleLayout',
]

_STRETCH_TYPE = 'stretch' # <stretch stretch=n> 伸缩占位组件的标签名
_STRETCH_KEY = 'stretch_item' # UIMLLayout 字典树中标记伸缩占位组件的键

# 解析阶段已消费的键，注册后由 Parser API 自动从结果中移除，不再传给 UIMLLayout 的字典树
used_widget_key = ['show_if']
used_layout_key = ['show_if', 'pressed']

def widget_replacer(ui_data: str):
    '''
    替换UI中的widget，使用函数式返回
    '''
    if not isinstance(ui_data, str):
        return ui_data # 如果不是字符串，直接返回原始数据 
    if ui_data.startswith('!lang '):
        if len(ui_data.split(' ')) == 2:
            return get_lang(ui_data.split(' ')[1]) # 语言解析
        else:
            return get_lang(ui_data.split(' ')[1], source=globals()[ui_data.split(' ')[2]]) # 语言解析
    else:
        return uiml.default_replacer(ui_data) # 交由uiml进行替换

def _is_stretch(ui_data):
    '''判断子组件是否为 <stretch stretch=n> 伸缩占位组件'''
    return isinstance(ui_data, dict) and ui_data.get('type') == _STRETCH_TYPE

def _compile_stretch(ui_data):
    '''编译伸缩占位组件，返回 UIMLLayout 可识别的伸缩标记'''
    if not ui_data.get('show_if', True):
        return None
    stretch = ui_data.get('stretch', 1)
    return {'name': ui_data.get('name', _STRETCH_TYPE), _STRETCH_KEY: True, 'stretch': stretch if isinstance(stretch, int) else 1}

def _compile_content(ui_data, namespace, additional_value, allow_stretch=True):
    '''顺序编译布局的子组件，<stretch> 在 u 模式下禁用'''
    compiled_list = []
    for item in ui_data.get('content', []):
        if _is_stretch(item):
            compiled = _compile_stretch(item) if allow_stretch else None
        else:
            compiled = uiml.compile_ui(item, namespace, additional=additional_value) # 递归解析
        if compiled is None or compiled is uiml.NoPaint:
            continue
        compiled_list.append(compiled)
    return compiled_list

def _parse_layout(ui_data: dict[str, Any], namespace, additional_value):
    '''
    解析普通布局，等价于 uiml.default_layout_parser，额外支持 <stretch stretch=n> 子组件
    '''
    other_values = {k: v for k, v in ui_data.items() if k not in ('name', 'direction', 'content', 'stretch')}
    return {'name': ui_data.get('name'), 'direction': ui_data.get('direction'), 'content': _compile_content(ui_data, namespace, additional_value), 'stretch': ui_data.get('stretch', False), **other_values}


def layout_parser(ui_data: dict[str, Any], namespace=None, additional=None):
    additional_value = additional if additional is not None else {} # 额外参数
    if not ui_data.get('show_if', True):
        return uiml.NoPaint # 不绘制，也不继续回退到其他解析器
    ui_data = {k: v for k, v in ui_data.items() if k not in used_layout_key} # 已消费的键不传给 UIMLLayout
    if ui_data.get('direction').lower() == 'u':
        # 索引0 -- 字
        # 索引1 -- 输入框
        # 索引2 -- 选择框
        inputs = ui_data['content'][1]
        combos = ui_data['content'][2] # 组合框
        return {
            'name': ui_data.get('name'), 'direction': ui_data.get('direction'), 
            "texts": ui_data['content'][0]['values'], 
            'inputs': _compile_content(inputs, namespace, additional_value, allow_stretch=False), 
            'combos': _compile_content(combos, namespace, additional_value, allow_stretch=False)
        }

    return _parse_layout(ui_data, namespace, additional_value) # 支持 <stretch> 的布局解析

def _move_content(d):
    '''移动 content，同义转换'''
    contents = d.pop("content", [])
    for item in contents:
        if not isinstance(item, dict):
            continue
        key = item.get("type")
        if key is None:
            continue
        d.setdefault(key, item.get("content"))  # 根里已有同名键时不覆盖
    return d

def widget_parser(ui_data: dict[str, Any], namespace=None, additional=None):
    from PySide6.QtCore import QEasingCurve

    additional_value = additional if additional is not None else {} # 额外参数
    show_value = ui_data.get('show_if', True)
    if not show_value:
        return uiml.NoPaint # 不绘制，也不继续回退到其他解析器

    if ui_data['type'] == 'bubble::Expander':
        _move_content(ui_data)

        for key in list(ui_data.keys()):  # 用 list 复制键，避免遍历时修改字典结构
            if key not in ('name', 'type'):
                ui_data[key] = widget_replacer(ui_data[key])

        headericon = ui_data.get('headerIcon', None)

        if isinstance(headericon, list):
            show_headericon = widget_parser(headericon[0], namespace, additional_value)['content']
        elif isinstance(headericon, str):
            show_headericon = FontIcon(headericon, size=20)

        header = ui_data.get('header', None)
        description = ui_data.get('description', None)

        right_layout = ui_data.get('rightLayout', [])

        if len(right_layout) > 1 :
            raise uiml.UIMLException(f'The component "bubble::Expander.rightLayout" must have zero or one child component')
        elif len(right_layout) == 1:
            if right_layout[0]['type'] != 'layout':
                raise uiml.UIMLException(f'The child component type of "bubble::Expander.rightLayout" must be "uiml::layout"')

            right_layout_window = uiml.UIMLLayout(uiml.compile_ui(right_layout[0], namespace, additional_value)).show() # 编译ui
        elif len(right_layout) == 0:
            right_layout_window = None

        expanded_layout = ui_data.get('ExpandedLayouts', [])
        expanded_line = [] # 展开列表
        for item in expanded_layout:
            if item.get('type') == 'ExpandedItem':
                if len(item.get('content', [])) != 2:
                    raise uiml.UIMLException(f'The component "bubble::Expander.ExpandedLayouts.ExpandedItem" must have two child components')
                left_item = uiml.UIMLLayout(uiml.compile_ui(item['content'][0], namespace, additional_value)).show() # 编译左侧菜单
                right_item = uiml.UIMLLayout(uiml.compile_ui(item['content'][1], namespace, additional_value)).show() # 编译右侧菜单
                expanded_line.append(create_expander_row(left_item, right_item, press_command=item.get('pressed', None)))
            elif item.get('type') == 'layout':
                pressed = item.get('pressed', None)
                layout = uiml.UIMLLayout(uiml.compile_ui(item, namespace, additional_value)).show() # 编译ui

                if pressed:
                    expanded_line.append(PressableRow(layout, pressed))
                else:
                    expanded_line.append(layout)
            else:
                raise uiml.UIMLException(f'The child component type of "bubble::Expander.ExpandedLayouts" must be "uiml::layout" or "bubble::Expander.ExpandedLayouts.ExpandedItem"') # 特殊布局必须是 layout

        return {
            'name': ui_data.get('name'), 
            'content': Expander(
                title=show_headericon, 
                subtitle=header, 
                description=description,
                right_layout=right_layout_window, 
                layouts=expanded_line,
                expanded=ui_data.get('expanded', False), 
                duration=ui_data.get('duration', 250), 
            )
        }
    elif ui_data['type'] == 'bubble::PressableLayout': # 按下布局
        pressed = ui_data.get('pressed', None)

        content = ui_data.get('content', [])
        if len(content) > 1:
            raise uiml.UIMLException(f'The component "bubble::PressableRow" must have zero or one child component')
        elif len(content) == 1:
            if content[0]['type'] != 'layout':
                raise uiml.UIMLException(f'The child component type of "bubble::PressableRow" must be "uiml::layout"')
            layout = uiml.UIMLLayout(uiml.compile_ui(content[0], namespace, additional_value)).show() # 编译ui
            return {
                'name': ui_data.get('name'), 
                'content': PressableRow(layout, pressed)
            }
    elif ui_data['type'] == 'bubble::fonticon':
        widget = FontIcon(widget_replacer(ui_data.get('glyph', '')), size=ui_data.get('size', 14), color=ui_data.get('color', None))

        return {
            'name': ui_data.get('name'), 
            'content': widget
        }
    elif ui_data['type'] == 'bubble::Card':
        _move_content(ui_data)

        layout = ui_data.get('layout', '')

        if len(layout) > 1:
            raise uiml.UIMLException(f'The component "bubble::Card.layout" must have zero or one child component')
        elif len(layout) == 1:
            if layout[0]['type'] != 'layout':
                raise uiml.UIMLException(f'The child component type of "bubble::Card" must be "uiml::layout"') # 特殊布局必须是 layout
            show_layout = uiml.UIMLLayout(uiml.compile_ui(layout[0], namespace, additional_value)).show() # 编译ui

        return {
            'name': ui_data.get('name'), 
            'content': Card(show_layout)
        }
    elif ui_data['type'] == 'bubble::contentCard':
        _move_content(ui_data)

        for key in list(ui_data.keys()):  # 用 list 复制键，避免遍历时修改字典结构
            if key not in ('name', 'type'):
                ui_data[key] = widget_replacer(ui_data[key])

        headericon = ui_data.get('headerIcon', None)

        if isinstance(headericon, list):
            show_headericon = widget_parser(headericon[0], namespace, additional_value)['content']
        elif isinstance(headericon, str):
            show_headericon = FontIcon(headericon, size=20)

        header = ui_data.get('header', None)
        description = ui_data.get('description', None)

        layout = ui_data.get('rightLayout', [])

        if len(layout) > 1 :
            raise uiml.UIMLException(f'The component "bubble::Expander.rightLayout" must have zero or one child component')
        elif len(layout) == 1:
            if layout[0]['type'] != 'layout':
                raise uiml.UIMLException(f'The child component type of "bubble::Expander.rightLayout" must be "uiml::layout"')

            layout_window = uiml.UIMLLayout(uiml.compile_ui(layout[0], namespace, additional_value)).show() # 编译ui
        elif len(layout) == 0:
            layout_window = None

        return {
            'name': ui_data.get('name'), 
            'content': ContentCard(
                title=show_headericon, 
                subtitle=header, 
                description=description, 
                wrap_threshold=ui_data.get('maxWarp', 475), 
                no_icon_threshold=ui_data.get('maxNoIcon', 100), 
                right_layout=layout_window
            )
        }
    elif ui_data['type'] == 'bubble::toggleSwitch':
        state_text = (ui_data.get('offText', None), ui_data.get('onText', None))
        off, on = state_text[0], state_text[1]

        if off is None and on is None:
            state = None
        elif off is None or on is None:
            print('Warning: bubble::toggleSwitch must have offText and onText, but one of them is None. So it will use default value.')
            state = None
        else:
            state = state_text

        widget = ToggleSwitch(
            state_text = state,

            checked = ui_data.get('checked', False), 
            track_width = ui_data.get('width', 40), 
            track_height = ui_data.get('height', 20), 
            animation_duration = ui_data.get('duration', 250), 
            easing_curve = ui_data.get('easing_curve', QEasingCurve.OutCubic), 
        )

        for sign, func in ui_data.get('signals', {}).items():
            getattr(widget, sign).connect(func) # 连接信号，需要专门处理

        return {
            'name': ui_data.get('name'), 
            'content': widget
        }

    return uiml.default_widget_parser(ui_data, namespace, additional_value) # 交由 uiml 进行处理
    
class BubbleLayout(uiml.UIMLLayout):
    def __init__(self, list=None):
        super().__init__(list)

    def layout_loader(self, current, part):
        direction = current.get('direction', '').lower()

        if direction == 'u':
            # 特殊布局：返回 texts、inputs、combos 组成的字典
            return {
                'texts': current.get('texts', []),
                'inputs': current.get('inputs', []),
                'combos': current.get('combos', [])
            }
        return super().layout_loader(current, part) # 交给 UIML 进行操作

    def subelement_finder(self, current, next):
        # 从 inputs 和 combos 中查找子元素
        direction = current.get('direction', '').lower()

        if direction == 'u':
            for child in current.get('inputs', []) + current.get('combos', []):
                if child.get('name') == next:
                    found = child
                    return found
        return super().subelement_finder(current, next)
    
    def return_layout(self, layout):
        return layout, 'layout', 0

    def extend_layout(self, list_info):
        if list_info['direction'].lower() == 'u':
            layout = UnitInputLayout()
            for text, input, combo in zip(list_info['texts'], list_info['inputs'], list_info['combos']):
                if text.startswith('!lang '): # 语言解析
                    text = get_lang(text[6:])
                layout.addUnitRow(text, input['content'], combo['content'])
            return layout, 'layout', 0
        else:
            return super().extend_layout(list_info) # 未知方向交给 uiml 抛出 UIMLException
            
    def adder(self, widget_info):
        return (widget_info[0], ), {'stretch': widget_info[2]}
    
    def add_layout(self, list_content: dict, layout: uiml.QLayout):
        draw_on_end = list_content.get('stretch_place', 'end') == 'end' # 是否在布局末尾绘制拉伸
        if not draw_on_end: # 在布局前绘制拉伸
            self._add_stretch(list_content, layout) # 添加伸缩
        self._for_loop(list_content, layout) # 递归绘制子布局
        if draw_on_end: # 在布局末尾绘制拉伸
            self._add_stretch(list_content, layout) # 添加伸缩
        return self.return_layout(layout)

    def _for_loop(self, list_content, layout):
        for item in list_content['content']:
            if item.get(_STRETCH_KEY): # <stretch stretch=n>，相当于在此处 AddStretch(n)
                layout.addStretch(item.get('stretch', 1))
                continue
            widget = self.draw_layout(item)
            if widget is uiml.NoPaint: # 该节点不绘制
                continue
            if widget[1] == 'widget':
                func = layout.addWidget
            elif widget[1] == 'layout':
                func = layout.addLayout
            else:
                raise ValueError('Content must be a widget or a layout')
            adder = self.adder(widget)
            func(*adder[0], **adder[1])
            
    def extend_widget(self, widget_info):
        widget = super().extend_widget(widget_info)
        if widget is uiml.NoPaint: # 该组件不绘制
            return uiml.NoPaint
        widget = list(widget)
        widget.append(widget_info.get('stretch', 0))
        return tuple(widget)

# 注册到 uiml 的解析器/字段列表；reset=True 时需要能移除后重新注册
_PARSER_ITEMS = (
    (uiml.ParserEnum.replacer, widget_replacer),
    (uiml.ParserEnum.widget_parser, widget_parser),
    (uiml.ParserEnum.layout_parser, layout_parser),
    (uiml.ParserEnum.uiml_class, BubbleLayout),
)

_USED_KEY_ITEMS = (
    (uiml.UsedKeyEnum.widget, used_widget_key),
    (uiml.UsedKeyEnum.layout, used_layout_key),
)

_registered = False


def register_parser(reset: bool = False):
    '''
    一键注册本项目对 uiml 的全部扩展（新版 Parser API）。

    注册内容：
    - `ParserEnum.replacer`：`widget_replacer`（`!lang` 语言替换）
    - `ParserEnum.widget_parser`：`widget_parser`（bubble:: 组件）
    - `ParserEnum.layout_parser`：`layout_parser`（支持 `u` 方向与 `<stretch>`）
    - `ParserEnum.uiml_class`：`uiml.UIMLLayout`（自定义渲染类）
    - `UsedKeyEnum.widget` / `UsedKeyEnum.layout`：`show_if`、`pressed` 等自定义字段

    参数:
        reset: 为 `True` 时先恢复 uiml 的默认解析器和字段列表，再重新注册；
               默认为 `False`，只注册一次。

    用法:
        from .old import register_parser

        register_parser()

    注意:
        注册后 `uiml.compile_ui(...)` 会自动使用本项目的解析器；
        `uiml.UIMLLayout(data)` 会返回 `uiml.UIMLLayout` 实例。
        不能与旧版 Namespace API 混用，请勿再调用
        `uiml.enable_namespace_api()` / `uiml.set_namespace(...)`。
    '''
    global _registered

    if uiml.namespace_api_enabled:
        raise RuntimeError(
            'register_parser() uses Parser API, please disable Namespace API first.'
        )

    if reset: # 先恢复默认解析器/字段列表，避免重复注册
        for enum, _ in _PARSER_ITEMS:
            uiml.add_parser(enum, uiml.ControlEnum.reset)
        for enum, _ in _USED_KEY_ITEMS:
            uiml.add_used_key(enum, uiml.ControlEnum.reset)
        _registered = False

    if _registered: # 已注册过，直接返回
        return

    for enum, parser in _PARSER_ITEMS:
        uiml.add_parser(enum, parser)
    for enum, keys in _USED_KEY_ITEMS:
        uiml.add_used_key(enum, keys)

    _registered = True