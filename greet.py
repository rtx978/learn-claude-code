def greet(name):
    """Return a greeting message for the given name.
    
    Args:
        name: The name of the person to greet.
    
    Returns:
        A greeting string in the format "Hello, {name}!"
    """
    return f"Hello, {name}!"


class SegmentTree:
    """线段树模板 - 支持区间查询和更新"""
    
    def __init__(self, arr):
        """初始化线段树
        
        Args:
            arr: 输入数组
        """
        self.n = len(arr)
        self.tree = [0] * (4 * self.n)
        if self.n > 0:
            self._build(arr, 0, 0, self.n - 1)
    
    def _build(self, arr, node, start, end):
        """构建线段树"""
        if start == end:
            self.tree[node] = arr[start]
        else:
            mid = (start + end) // 2
            self._build(arr, 2 * node + 1, start, mid)
            self._build(arr, 2 * node + 2, mid + 1, end)
            self.tree[node] = self.tree[2 * node + 1] + self.tree[2 * node + 2]
    
    def query(self, left, right):
        """区间查询 [left, right] 的和
        
        Args:
            left: 区间左端点
            right: 区间右端点
        
        Returns:
            区间和
        """
        return self._query(0, 0, self.n - 1, left, right)
    
    def _query(self, node, start, end, left, right):
        """递归查询"""
        if right < start or left > end:
            return 0
        if left <= start and end <= right:
            return self.tree[node]
        mid = (start + end) // 2
        return (self._query(2 * node + 1, start, mid, left, right) +
                self._query(2 * node + 2, mid + 1, end, left, right))
    
    def update(self, idx, value):
        """单点更新
        
        Args:
            idx: 更新位置
            value: 新值
        """
        self._update(0, 0, self.n - 1, idx, value)
    
    def _update(self, node, start, end, idx, value):
        """递归更新"""
        if start == end:
            self.tree[node] = value
        else:
            mid = (start + end) // 2
            if idx <= mid:
                self._update(2 * node + 1, start, mid, idx, value)
            else:
                self._update(2 * node + 2, mid + 1, end, idx, value)
            self.tree[node] = self.tree[2 * node + 1] + self.tree[2 * node + 2]