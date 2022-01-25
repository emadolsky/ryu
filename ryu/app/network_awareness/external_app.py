import requests
import copy
import networkx as nx
from networkx.algorithms.shortest_paths.generic import shortest_path
from networkx.readwrite import json_graph
import argparse

MAX_CAPACITY = 281474976710655

class ExternalShortestPath():
    def __init__(self, k_paths, weight) -> None:
        self.k = k_paths
        self.weight = weight
        pass
        
    def get_min_bw_of_links(self, graph, path, min_bw):
        """
            Getting bandwidth of path. Actually, the mininum bandwidth
            of links is the bandwith, because it is the neck bottle of path.
        """
        _len = len(path)
        if _len > 1:
            minimal_band_width = min_bw
            for i in range(_len-1):
                pre, curr = path[i], path[i+1]
                if 'bandwidth' in graph[pre][curr]:
                    bw = graph[pre][curr]['bandwidth']
                    minimal_band_width = min(bw, minimal_band_width)
                else:
                    continue
            return minimal_band_width
        return min_bw

    def get_best_path_by_bw(self, graph, paths):
        """
            Get best path by comparing paths.
        """
        capabilities = {}
        best_paths = copy.deepcopy(paths)

        for src in paths:
            for dst in paths[src]:
                if src == dst:
                    best_paths[src][src] = [[src]]
                    capabilities.setdefault(src, {src: MAX_CAPACITY})
                    capabilities[src][src] = MAX_CAPACITY
                    continue
                max_bw_of_paths = 0
                best_path = paths[src][dst][0]
                for path in paths[src][dst]:
                    min_bw = MAX_CAPACITY
                    min_bw = self.get_min_bw_of_links(graph, path, min_bw)
                    if min_bw > max_bw_of_paths:
                        max_bw_of_paths = min_bw
                        best_path = path

                best_paths[src][dst] = [best_path]
                capabilities.setdefault(src, {dst: max_bw_of_paths})
                capabilities[src][dst] = max_bw_of_paths
        self.capabilities = capabilities
        self.best_paths = best_paths
        return capabilities, best_paths

    def k_shortest_paths(self, graph, src, dst):
        """
            Great K shortest paths of src to dst.
        """
        k = self.k
        generator = nx.shortest_simple_paths(graph, source=src,
                                             target=dst, weight=self.weight)
        shortest_paths = []
        try:
            for path in generator:
                if k <= 0:
                    break
                shortest_paths.append(path)
                k -= 1
            return shortest_paths
        except:
            print("No path between %s and %s" % (src, dst))

    def all_k_shortest_paths(self, graph):
        """
            Creat all K shortest paths between datapaths.
        """
        _graph = copy.deepcopy(graph)
        paths = {}

        # Find ksp in graph.
        for src in _graph.nodes():
            paths.setdefault(src, {src: [[src] for i in range(self.k)]})
            for dst in _graph.nodes():
                if src == dst:
                    continue
                paths[src].setdefault(dst, [])
                paths[src][dst] = self.k_shortest_paths(_graph, src, dst)
        
        if self.weight == "bw":
            results = self.get_best_path_by_bw(graph, paths)
            paths = results[1]
        return paths

if __name__ == "__main__":
    # Instantiate the parser
    parser = argparse.ArgumentParser(description='External network shortest path calculator app')
    parser.add_argument('--kpaths', type=int, help='k shortest paths', required=True)
    parser.add_argument('--weight', type=str, help='weight type of the links', required=True)
    args = parser.parse_args()

    spCalculator = ExternalShortestPath(args.kpaths, args.weight)
    res = requests.get("http://localhost:8080/v1.0/topology/graph")
    print(res.json())
    graph_link_data = res.json()
    g = json_graph.node_link_graph(graph_link_data)
    paths = spCalculator.all_k_shortest_paths(g)
    print(paths)
    requests.post("http://localhost:8080/v1.0/topology/shortest_path", json=paths)