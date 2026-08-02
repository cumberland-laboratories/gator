# Reference Note: Reinforcing Loops

## The Pattern

Every process in the system must have both an input source and an output consumer. No process produces dead-end output. No process consumes input that nothing produces. The system is a closed network of mutually reinforcing loops.

This is the design pattern that makes constitutional architecture tight: threads → wiki pipeline → enforcer audit → corrections → threads. Each process feeds another. The system iteratively improves through its own operation.

## Application to the Memex

The Memex must exhibit the same property. When evaluating a new process or feature, ask:
- **What feeds it?** (If nothing, it won't run.)
- **What does it feed?** (If nothing, it's a dead end — reconsider or connect it.)

## Current Loop Map

```
Conversation → thread updates → wiki pipeline → rendered documentation
     ↓                ↓
  hit counts    friction log
     ↓                ↓
  wiki weighting   enforcer review
     ↓                ↓
  promotion/      retag, resize,
  demotion        promote, wiki
     ↓                ↓
  budget compliance   thread improvements → better conversation
```

## The Test

If you can't trace a loop from any process back to itself (through other processes), something is disconnected. Fix the connection, don't add the feature.
