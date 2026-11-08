'''
组件样式
'''
import json
import re
from enum import Enum
from .QUI import *

__all__ = ['StyleReplaceMode', 'StyleSheet', 'styles', 'indexes', 'maps', 'style_path']

class StyleReplaceMode(Enum):
    '''
    特殊样式替换模式
    '''
    ALL = 'all'  # 全部替换

class StyleSheet:
    '''CSS序列化工具类，支持CSS与JSON互相转换'''
    
    def __init__(self, css_text):
        '''
        初始化CSS序列化器
        
        Args:
            css_text: CSS文本
        '''
        # 编译正则表达式以提高性能
        self.property_pattern = re.compile(r'\s*([^:]+)\s*:\s*([^;]+)\s*(?:;|$)')
        self.comment_pattern = re.compile(r'/\*.*?\*/', re.DOTALL)
        self.empty_line_pattern = re.compile(r'\n\s*\n')
        
        # 变量
        self.css_text = css_text
        self.css_data = self.serialize(css_text)
    
    def _clean_css(self, css: str) -> str:
        '''
        清理CSS：移除注释、多余空格和空行
        
        Args:
            css: 原始CSS字符串
            
        Returns:
            清理后的CSS字符串
        '''
        # 移除CSS注释
        css = self.comment_pattern.sub('', css)
        
        # 移除多余空格（保留必要的空格，如属性值中的空格）
        # 这里我们只移除选择器和属性名周围的空格
        css = css.strip()
        
        # 移除空行
        css = self.empty_line_pattern.sub('\n', css)
        
        return css

    def _parse_rule(self, selector: str, rule_body: str) -> dict[str, str]:
        '''
        解析单个CSS规则体
        
        Args:
            selector: CSS选择器
            rule_body: 规则体内容
            
        Returns:
            解析后的属性字典
        '''
        properties = {}

        # 查找所有属性
        matches = self.property_pattern.findall(rule_body)
        
        for prop_name, prop_value in matches:
            # 清理属性名和值
            prop_name = prop_name.strip()
            prop_value = prop_value.strip()
            
            if prop_name and prop_value:
                properties[prop_name] = prop_value
        
        return properties
    
    def _get_value_by_indices(self, indices, multi_list):
        '''
        根据索引列表逐层访问多维列表
        
        Args:
            indices: 一维索引列表，如 [0, 1]
            multi_list: 多维列表，如 [[1, 2], [3, 4]]
        
        Returns:
            对应位置的值
        '''
        result = multi_list
        for index in indices:
            result = result[index]
        return result
    
    def _update_nested_dict(self, keys, nested_dict, new_value):
        '''
        根据键列表更新嵌套字典中的值，中间层级不存在时会自动创建
        
        Args:
            keys: 键列表，如 ['a', 'b']
            nested_dict: 嵌套字典，如 {'a': {'b': 'c'}}
            new_value: 要设置的新值，如 'd'
        
        Returns:
            修改后的字典（原字典不会被修改）
        '''
        result = nested_dict.copy()
        current = result
        
        # 遍历到倒数第二个键，缺失时自动创建
        for key in keys[:-1]:
            child = current.get(key)
            if not isinstance(child, dict):
                child = {}
            else:
                child = child.copy()
            current[key] = child
            current = child
        
        # 用最后一个键设置新值
        current[keys[-1]] = new_value
        
        return result
    
    def serialize_to_jsonstr(self, css: str, indent: None | int = None) -> str:
        '''
        将CSS序列化为JSON字符串
        
        Args:
            css: CSS字符串
            indent: JSON缩进，None表示不缩进
            
        Returns:
            JSON格式字符串
        '''
        result = {}

        # 清理CSS
        css = self._clean_css(css)
        
        # 分割规则块
        # 查找所有规则：选择器 { 规则体 }
        rule_start = 0
        depth = 0  # 花括号深度
        current_selector = None
        current_rule_start = 0
        
        for i, char in enumerate(css):
            if char == '{':
                if depth == 0:
                    # 找到选择器
                    selector_text = css[rule_start:i].strip()
                    if selector_text:
                        current_selector = selector_text
                        current_rule_start = i + 1
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and current_selector:
                    # 规则结束
                    rule_body = css[current_rule_start:i]
                    
                    # 解析规则
                    properties = self._parse_rule(current_selector, rule_body)
                    if properties:
                        # 处理多个选择器（如 'p, a, div'）
                        selectors = [s.strip() for s in current_selector.split(',')]
                        for selector in selectors:
                            if selector:
                                if selector in result:
                                    # 合并重复选择器的属性
                                    result[selector].update(properties)
                                else:
                                    result[selector] = properties.copy()
                    
                    # 重置
                    current_selector = None
                    rule_start = i + 1
        
        return json.dumps(result, indent=indent)
    
    def serialize(self, css: str) -> dict:
        '''
        将CSS序列化为字典
        
        Args:
            css: CSS字符串
            
        Returns:
            序列化后的字典
        '''
        json_str = self.serialize_to_jsonstr(css)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError(f'无效的JSON格式: {json_str}')
    
    def deserialize(
        self, 
        json_input: str | dict, 
    ) -> str:
        '''
        将JSON反序列化为CSS
        
        Args:
            json_input: JSON字符串或字典
            style: CSS格式化样式
            indent: 缩进空格数（仅当style为PRETTY时有效）
            
        Returns:
            CSS字符串
        '''
        try:
            # 解析JSON输入
            if isinstance(json_input, str):
                data = json.loads(json_input)
            elif isinstance(json_input, dict):
                data = json_input
            else:
                raise ValueError('输入必须是JSON字符串或字典')
            
            css_rules = []
            
            for selector, properties in data.items():
                if not isinstance(properties, dict):
                    continue

                # 最小化格式：无空格
                rule = f'{selector}{{'
                rule += ';'.join([f'{prop}:{value}' for prop, value in properties.items()])
                rule += ';}'
                css_rules.append(rule)
            return ''.join(css_rules)            
        except json.JSONDecodeError as e:
            raise ValueError(f'无效的JSON格式: {e}')
        
    def refresh(self, css_text: str):
        '''
        刷新CSS文本并重新解析
        
        Args:
            css_text: 新的CSS文本
        '''
        self.css_text = css_text
        self.css_data = self.serialize(css_text)
        
    def replace(self, index, old_value: str | StyleReplaceMode, new_value: str, output_json: bool = True) -> dict:
        '''
        替换CSS数据中的值
        
        Args:
            index: 要替换值的索引
            old_value: 旧值；为 StyleReplaceMode.ALL 时直接覆盖，键不存在时自动创建
            new_value: 新值
            output_json: True 返回字典，False 返回 StyleSheet
            
        Returns:
            新的CSS数据字典或 StyleSheet
        '''
        data = self.css_data.copy()
        
        if old_value == StyleReplaceMode.ALL:
            # 全匹配：即使键不存在也会创建
            new_data = self._update_nested_dict(index, data, new_value)
            if output_json:
                return new_data
            return StyleSheet(self.deserialize(new_data))
        
        value = self._get_value_by_indices(index, data)
        
        if not isinstance(value, str):
            raise ValueError(f'索引{index}处的值不是字符串')
        
        new_data = self._update_nested_dict(index, data, value.replace(old_value, new_value))
        if output_json:
            return new_data
        return StyleSheet(self.deserialize(new_data))
