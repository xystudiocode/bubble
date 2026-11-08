DEFAULT_SOURCE = None
DEFAULT_LANG = None

def get_lang(id, source=None, lang=None, default=''):
    '''
    Get the language text from the source list.
    '''
    source = source or DEFAULT_SOURCE # 获取默认语言包
    lang = lang or DEFAULT_LANG # 获取默认语言

    if not (source and lang):
        print(f'Warning: Source or lang not set')
        return default

    for i in source:
        if i['lang_id'] == 0: # 设置默认语言包
            default_lang_text = i['lang_package']
        if i['lang_id'] == lang: # 设置目前语言包
            lang_text = i['lang_package']
    try:
        return lang_text[id]
    except KeyError:
        print(f'Warning: Language {id} not found')
        return default
    except UnboundLocalError:
        lang_text = {}
        return lang_text.get(id, default_lang_text[id])