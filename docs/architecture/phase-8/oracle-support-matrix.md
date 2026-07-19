# Oracle Support Matrix

| Version | Target |
|---------|--------|
| Oracle Database 19c | Required (vertical slice) |
| Oracle Database 21c | On customer request |
| Oracle Database 23ai | Required (certification matrix) |
| Oracle RAC 19c | Separate HA certification (8.10) |
| CDB/PDB | Required — connect to PDB SERVICE_NAME only |
| Oracle 11g / 12.1 | Out of support |
| Oracle 12.2 | Special customer cert only |

Driver: `python-oracledb` Thin Mode default. Thick Mode = separate deployment (`query-gateway-oracle-thick`); never switch mode mid-process.
