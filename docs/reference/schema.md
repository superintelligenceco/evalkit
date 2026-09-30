# Suite JSON Schema

`evalkit schema` prints this schema. Point your editor's YAML language server at it to get
completion and validation while you write a suite. For example, with the Red Hat YAML extension
for VS Code, save the output as `evalkit.schema.json` and add this line to the top of
`evals.yaml`:

```yaml
# yaml-language-server: $schema=./evalkit.schema.json
```

The schema below is generated from the suite models when the site builds.

<!-- evalkit:schema -->
