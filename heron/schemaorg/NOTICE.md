# Schema.org vocabulary - NOTICE

`schemaorg-29.3.json` is a compact index of the Schema.org vocabulary, release 29.3
(https://schema.org).

- Source: https://raw.githubusercontent.com/schemaorg/schemaorg/020b8681dad2e50c1dd9e2700a703b0bb1c5c6fa/data/releases/29.3/schemaorg-all-https.jsonld
- Commit: `020b8681dad2e50c1dd9e2700a703b0bb1c5c6fa`
- sha256: `3accdd18eb0b1e118938de8fb301ad0e332ed8e7b27ccecf3f753a8712ad1d73` (1 500 091 bytes)
- License: Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0),
  https://creativecommons.org/licenses/by-sa/3.0/
- Attribution: Schema.org vocabulary, release 29.3, https://schema.org; compacted into an index by HERON.

Modified: compacted into an index (types, parents, properties with domains and ranges,
enumeration members, sections, deprecation marks). Term descriptions are not included.

The index is shared vocabulary data, the same for every site. The license of the HERON
engine itself does not change.

Rebuild (byte-for-byte reproducible):

```bash
python3 scripts/schemaorg_index.py --source schemaorg-all-https.jsonld
# without --source the file is downloaded from the pinned commit above
```
