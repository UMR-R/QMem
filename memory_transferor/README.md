# memory_transferor

`memory_transferor` is the canonical memory pipeline planned for Memory Assistant.

It owns the product memory path:

```text
RawChatSession -> RawChatTurn -> Episode -> PersistentMemory
```

External indexes such as ChromaDB must be derived from this canonical storage;
they are not the source of truth.

