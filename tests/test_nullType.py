class NullType:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

def test_nullType():
    null = NullType(None)(12)