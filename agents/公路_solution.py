class HookSystem:
    def __init__(self):
        self.hooks = {}

    # 注册钩子
    def register(self, event, func):
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(func)

    # 触发钩子
    def trigger(self, event, *args, **kwargs):
        for func in self.hooks.get(event, []):
            func(*args, **kwargs)


# 使用
hook = HookSystem()

def before_run():
    print("我是 Hook，运行前插一脚")

# 注册
hook.register("before_run", before_run)

# 主流程
print("主流程开始")
hook.trigger("before_run")  # 触发钩子
print("主流程结束")