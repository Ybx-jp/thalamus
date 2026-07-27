// Gremlin Server initialization script.
//
// Binds the traversal source Thalamus connects to. `substrate/writer.py` opens
// ws://localhost:8182/gremlin with the source name "g"; this is the other end of
// that contract.
def globals = [:]
globals << [g: traversal().withEmbedded(graph)]
