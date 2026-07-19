"""OData metadata parser tests."""

from __future__ import annotations

from query_gateway.infrastructure.sap.odata.metadata_parser import (
    filter_published_entities,
    parse_metadata_xml,
)

SAMPLE = """<?xml version="1.0"?>
<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
  <edmx:DataServices>
    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="SAP">
      <EntityType Name="JournalEntryItemType">
        <Key><PropertyRef Name="CompanyCode"/></Key>
        <Property Name="CompanyCode" Type="Edm.String" Nullable="false"/>
        <Property Name="AmountInCompanyCodeCurrency" Type="Edm.Decimal" Precision="23" Scale="2"/>
        <Property Name="CompanyCodeCurrency" Type="Edm.String" MaxLength="5"
          sap:semantics="currency-code" xmlns:sap="http://www.sap.com/Protocols/SAPData"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="JournalEntryItem" EntityType="SAP.JournalEntryItemType"/>
        <EntitySet Name="SecretInternal" EntityType="SAP.JournalEntryItemType"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""


def test_parse_and_fingerprint():
    meta = parse_metadata_xml(SAMPLE, service_name="API_JOURNALENTRYITEM_SRV", api_version="V4")
    assert meta["fingerprint"]
    assert any(e["name"] == "JournalEntryItem" for e in meta["entitySets"])
    assert "JournalEntryItemType" in meta["entityTypes"]


def test_filter_allowed_only():
    meta = parse_metadata_xml(SAMPLE, service_name="API_JOURNALENTRYITEM_SRV")
    filtered = filter_published_entities(meta, {"JournalEntryItem"})
    names = {e["name"] for e in filtered["entitySets"]}
    assert names == {"JournalEntryItem"}
