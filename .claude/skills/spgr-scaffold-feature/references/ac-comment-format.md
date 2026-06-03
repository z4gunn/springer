# Acceptance-criteria TODO comment format

Pre-fill each acceptance criterion as one TODO comment in every relevant stub. Use a single fixed format so the acceptance-test generator (spgr-write-acceptance-test) and the implementing agent read the same contract.

## Format

One criterion per line, in the host language's line-comment syntax, with this shape:

```
TODO(AC-<id>): <Given/When/Then criterion text verbatim>
```

- `AC-<id>` is the criterion ID from the story's acceptance-criteria set. Keep it stable so a test can be traced back to a criterion.
- The text is the criterion verbatim, including the Given/When/Then clauses. Do not paraphrase, because the test generator parses this text.
- Place the comments at the top of the layer's primary unit (the handler, the service method, the test case) so they sit next to the code that will satisfy them.

## Examples

Backend service stub (Python):

```python
# TODO(AC-1): Given a valid payload, When the user submits, Then a record is created and 201 is returned
# TODO(AC-2): Given a payload missing the email field, When the user submits, Then 422 is returned with a field error
def create_widget(payload):
    raise NotImplementedError
```

Acceptance test stub (JavaScript):

```javascript
// TODO(AC-1): Given a valid payload, When the user submits, Then a record is created and 201 is returned
test.todo("AC-1 creates a record on valid submit");
```

## Machine readability

The fixed `TODO(AC-<id>):` prefix is the parse anchor. A downstream tool greps for that prefix, splits on the first colon, and keeps the ID and the criterion text. Do not add free-form notes on the same line, since they break the parse. Put any extra note on a separate plain comment line.
