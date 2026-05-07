public class SegmentTree {
    private int n;
    private int[] tree;
    private int[] lazy;

    public SegmentTree(int[] nums) {
        this.n = nums.length;
        this.tree = new int[4 * n];
        this.lazy = new int[4 * n];
        build(1, 0, n - 1, nums);
    }

    private void build(int node, int start, int end, int[] nums) {
        if (start == end) {
            tree[node] = nums[start];
        } else {
            int mid = (start + end) / 2;
            build(2 * node, start, mid, nums);
            build(2 * node + 1, mid + 1, end, nums);
            tree[node] = tree[2 * node] + tree[2 * node + 1];
        }
    }

    private void pushDown(int node, int start, int end) {
        if (lazy[node] != 0) {
            int mid = (start + end) / 2;
            int leftNode = 2 * node;
            int rightNode = 2 * node + 1;
            tree[leftNode] += lazy[node] * (mid - start + 1);
            tree[rightNode] += lazy[node] * (end - mid);
            lazy[leftNode] += lazy[node];
            lazy[rightNode] += lazy[node];
            lazy[node] = 0;
        }
    }

    public void updateRange(int l, int r, int val) {
        update(1, 0, n - 1, l, r, val);
    }

    private void update(int node, int start, int end, int l, int r, int val) {
        if (r < start || end < l) return;
        if (l <= start && end <= r) {
            tree[node] += val * (end - start + 1);
            lazy[node] += val;
        } else {
            pushDown(node, start, end);
            int mid = (start + end) / 2;
            update(2 * node, start, mid, l, r, val);
            update(2 * node + 1, mid + 1, end, l, r, val);
            tree[node] = tree[2 * node] + tree[2 * node + 1];
        }
    }

    public int queryRange(int l, int r) {
        return query(1, 0, n - 1, l, r);
    }

    private int query(int node, int start, int end, int l, int r) {
        if (r < start || end < l) return 0;
        if (l <= start && end <= r) return tree[node];
        pushDown(node, start, end);
        int mid = (start + end) / 2;
        int leftSum = query(2 * node, start, mid, l, r);
        int rightSum = query(2 * node + 1, mid + 1, end, l, r);
        return leftSum + rightSum;
    }

    public static void main(String[] args) {
        int[] nums = {1, 3, 5, 7, 9, 11};
        SegmentTree st = new SegmentTree(nums);
        
        // 区间更新：将[0,3]区间元素加2
        st.updateRange(0, 3, 2);
        
        // 查询区间和：[0,3]的和应为 (1+2)+(3+2)+(5+2)+(7+2) = 3+5+7+9=24
        System.out.println("区间和为: " + st.queryRange(0, 3));
    }
}