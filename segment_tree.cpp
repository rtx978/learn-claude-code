#include <iostream>
#include <vector>
using namespace std;

class SegmentTree {
private:
    vector<int> tree;
    int size;

    void build(int node, int l, int r, const vector<int>& nums) {
        if (l == r) {
            tree[node] = nums[l];
            return;
        }
        int mid = (l + r) / 2;
        build(2*node, l, mid, nums);
        build(2*node+1, mid+1, r, nums);
        tree[node] = tree[2*node] + tree[2*node+1];
    }

    void update(int node, int l, int r, int idx, int value) {
        if (l == r) {
            tree[node] = value;
            return;
        }
        int mid = (l + r) / 2;
        if (idx <= mid) update(2*node, l, mid, idx, value);
        else update(2*node+1, mid+1, r, idx, value);
        tree[node] = tree[2*node] + tree[2*node+1];
    }

    int query(int node, int l, int r, int ql, int qr) {
        if (r < ql || l > qr) return 0;
        if (ql <= l && r <= qr) return tree[node];
        int mid = (l + r) / 2;
        return query(2*node, l, mid, ql, qr) + query(2*node+1, mid+1, r, ql, qr);
    }

public:
    SegmentTree(const vector<int>& nums) {
        size = 1;
        while (size < nums.size()) size <<= 1;
        tree.resize(2*size, 0);
        build(1, 0, nums.size()-1, nums);
    }

    void update(int idx, int value) {
        update(1, 0, size-1, idx, value);
    }

    int query(int ql, int qr) {
        return query(1, 0, size-1, ql, qr);
    }
};

int main() {
    vector<int> nums = {1, 3, 5, 7, 9, 11};
    SegmentTree st(nums);
    cout << "Original sum [0,5]: " << st.query(0,5) << endl;
    st.update(2, 10);
    cout << "After update, sum [0,5]: " << st.query(0,5) << endl;
    return 0;
}