## Design Notes

### Result handling

Operations that can fail as part of normal application flow return `Result[T]`
rather than raising exceptions.

`Result[T]` is a discriminated union of `Success[T]` and `Failure`. A success
contains a non-optional payload; a failure contains error information but no
payload.

The `ok` field is a literal discriminator (`True` / `False`) so Pyright can
narrow the result type. Code that needs the payload therefore uses:

```python
if result.ok is False:
    return result

payload = result.payload
```

This syntax is intentional: it is required for Pyright's discriminated-union.
Pyright will not narrow the result type when `result.ok` is tested using normal 
boolean negation (`if not result.ok`). The discriminator must be explicitly compared
with `True` or `False`.

Unexpected failures may still raise exceptions. `unwrap()` is used where
failure is explicitly converted into an exception.