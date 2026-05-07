# P12849 [Lanqiao Cup 2025 National A] Highway

import sys
sys.setrecursionlimit(500000)

def solve():
    input = sys.stdin.readline
    n = int(input())
    
    adj = [[] for _ in range(n + 1)]
    for _ in range(n - 1):
        u, v, w = map(int, input().split())
        adj[u].append((v, w))
        adj[v].append((u, w))
    
    sz = [0] * (n + 1)
    
    from collections import defaultdict
    
    dp = [defaultdict(int) for _ in range(n + 1)]
    
    def dfs1(u, p):
        sz[u] = 1
        for v, w in adj[u]:
            if v == p:
                continue
            dfs1(v, u)
            sz[u] += sz[v]
    
    dfs1(1, 0)
    
    ans = 0
    
    def dfs2(u, p):
        nonlocal ans
        
        for v, w in adj[u]:
            if v == p:
                continue
            dfs2(v, u)
            
            for x, cnt in dp[v].items():
                dp[u][x] += cnt
            dp[u][w] += sz[v]
        
        for v, w in adj[u]:
            if v == p:
                continue
            
            same_company_size = dp[u].get(w, 0) - sz[v]
            contrib_uv = sz[v] * (n - sz[v]) - sz[v] * same_company_size
            
            same_company_size_v = dp[v].get(w, 0)
            contrib_vu = sz[v] * (n - sz[v]) - sz[v] * same_company_size_v
            
            ans += contrib_uv + contrib_vu

    dfs2(1, 0)
    print(ans)

if __name__ == "__main__":
    solve()