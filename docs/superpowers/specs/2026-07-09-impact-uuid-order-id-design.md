# Impact UUID Order ID Support

## Goal

Support both legacy Impact order identifiers and native UUID order identifiers
without requiring a configured list of migrated markets.

## Identifier Resolution

Add a small resolver at the boundary where an Impact action is prepared for an
Order Service request.

- Preserve the original `Oid` as a string for logs, timing context, CSV output,
  and result summaries.
- If `Oid` is a valid UUID, normalize it to the canonical UUID string and pass
  it directly to Order Service.
- If `Oid` contains only decimal digits, preserve the current behavior and
  convert it with `OrderMiiUUID(market, order_id)`.
- Reject missing, empty, or otherwise invalid values with a descriptive
  `ValueError`.

Format-based resolution makes migration transparent to the bot and avoids
maintaining a market migration list.

## Processing Flow

Both the parallel prefetch loop and the main action-processing loop will use
the same resolver. This prevents the two paths from choosing different Order
Service identifiers.

The unused integer conversion of `AdId` will be removed. Failed identifier
resolution will follow the existing per-action error path and mark the action
as `Not_Processed`; error handling will use the raw `Oid` initialized before
resolution so it cannot reference an unassigned local variable.

No changes are required in `PATAClient`: its `retrieve_order` method already
accepts an arbitrary string identifier in the request URL.

## Compatibility

Legacy example:

```text
Oid: 12345
Order Service ID: 8637e025-ae91-48de-<country>-000000003039
Reported orderId: 12345
```

Migrated example:

```text
Oid: 550e8400-e29b-41d4-a716-446655440000
Order Service ID: 550e8400-e29b-41d4-a716-446655440000
Reported orderId: 550e8400-e29b-41d4-a716-446655440000
```

## Tests

Unit tests will verify:

- Numeric `Oid` still produces the existing deterministic legacy UUID.
- Native UUID `Oid` is passed through in canonical form.
- Uppercase UUID input is accepted and normalized.
- Missing, empty, and malformed `Oid` values are rejected.
- UUID handling is used consistently by the market-processing path and does
  not attempt integer conversion.

The existing test suite will be run after the focused tests pass.
