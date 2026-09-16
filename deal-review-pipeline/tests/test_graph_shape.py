from app.graph.workflow import build_graph

def test_langgraph_compiles():
    graph=build_graph()
    assert graph is not None
