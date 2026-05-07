n = 4
adj = {1: [(2,1),(3,1),(4,2)], 2: [(1,1)], 3: [(1,1)], 4: [(1,2)]}

def get_path_edges(s, t):
    parent = {}
    edge_w = {}
    from collections import deque
    q = deque([s])
    parent[s] = None
    while q:
        u = q.popleft()
        if u == t:
            break
        for v,w in adj[u]:
            if v not in parent:
                parent[v] = u
                edge_w[v] = w
                q.append(v)
    
    edges = []
    cur = t
    while cur is not None and cur != s:
        edges.append((parent[cur], cur, edge_w[cur]))
        cur = parent[cur]
    edges.reverse()
    return edges

edge_counts = {}
for u,v,w in [(1,2,1),(1,3,1),(1,4,2)]:
    edge_counts[(u,v,w)] = 0
    edge_counts[(v,u,w)] = 0

for s in range(1, n+1):
    for t in range(1, n+1):
        if s == t:
            continue
        edges = get_path_edges(s, t)
        prev_w = 0
        for i, (u,v,w) in enumerate(edges):
            if prev_w != w:
                edge_counts[(u,v,w)] += 1
            prev_w = w

print("Edge counts:")
for (u,v,w), cnt in edge_counts.items():
    print(f"  ({u},{v},{w}): {cnt}")
    
print("Total:", sum(edge_counts.values()))