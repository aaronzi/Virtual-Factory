# ADR-0017: Line commands as AAS Operations delegated to an operations gateway

- Status: accepted; refined by [ADR-0020](0020-control-component-and-aid-drive-commands.md): the gateway takes topics,
  flags and payload keys from LineControl → Control Component Instance → AID (no longer from `uns.json`);
  `ExecuteSkill` added
- Date: 2026-10-03

## Context
IT systems, workflows and AI agents should command the line through its AAS, not through MQTT topics they would have
to know. Control Component 2.0 (ADR-0012) describes skills and endpoints but has no invocable operations. BaSyx Go
1.1.0 supports operation invocation with **invocation delegation** (qualifier `invocationDelegation` = URL); the
delegate URL must be allow-listed (`SMREPO_DELEGATION_TRUSTED_HOSTS`), including the resolved IP address.

## Decision
- Custom template **LineControl** (LINE01) with Operations `ExecutePackMLCommand(Command)`, `ExchangeContainer(Container)`
  and `SetAutoExchange(Enabled)`, each with outputs `Accepted`, (`State`), `Message`, references to the controller
  AAS, its Control Component Instance and the current-state element.
- Each operation carries the delegation qualifier → `http://ops-gateway:8095/operations/<name>`.
- The **ops gateway** checks the request against the PackML state model (rejects disallowed commands with the
  allowed ones in the message), sends the command on the UNS (AID action), waits for the acknowledgement and - for
  PackML - for the target state (state history, so transient states like IDLE after Reset are not missed).
- The gateway runs with a fixed IP in the compose network (172.30.42.95) because of BaSyx's resolved-address check.

## Consequences
+ One call on the AAS (`POST .../LineControl/.../ExecutePackMLCommand/invoke`) starts or holds the line, end to end in
  well under a second; the BPMN order process uses the same path.
+ Rejections are explicit and explain the state model (useful for training and for agents).
− The delegation allow-list is deployment configuration (host + IP); a different network layout needs an update.
