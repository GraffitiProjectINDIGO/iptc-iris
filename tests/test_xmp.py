"""Tests for parsing IPTC Image Region data from XMP packets."""

from iptc_iris import normalize_metadata, parse_xmp


def test_parses_minimal_xmp_image_region():
    xmp = """<?xpacket begin=""?>
    <x:xmpmeta xmlns:x="adobe:ns:meta/">
      <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
        <rdf:Description rdf:about="">
          <Iptc4xmpExt:ImageRegion>
            <rdf:Bag>
              <rdf:li rdf:parseType="Resource">
                <Iptc4xmpExt:rId>face-1</Iptc4xmpExt:rId>
                <Iptc4xmpExt:RegionBoundary rdf:parseType="Resource">
                  <Iptc4xmpExt:rbShape>rectangle</Iptc4xmpExt:rbShape>
                  <Iptc4xmpExt:rbUnit>relative</Iptc4xmpExt:rbUnit>
                  <Iptc4xmpExt:rbX>0.1</Iptc4xmpExt:rbX>
                  <Iptc4xmpExt:rbY>0.2</Iptc4xmpExt:rbY>
                  <Iptc4xmpExt:rbW>0.3</Iptc4xmpExt:rbW>
                  <Iptc4xmpExt:rbH>0.4</Iptc4xmpExt:rbH>
                </Iptc4xmpExt:RegionBoundary>
              </rdf:li>
            </rdf:Bag>
          </Iptc4xmpExt:ImageRegion>
        </rdf:Description>
      </rdf:RDF>
    </x:xmpmeta>
    <?xpacket end="w"?>"""

    metadata = parse_xmp(xmp)
    result = normalize_metadata(metadata).validation_result()

    assert metadata["imageRegion"][0]["rId"] == "face-1"
    assert result.valid


def test_parses_xmp_alt_language_values_as_mapping():
    xmp = """
    <x:xmpmeta xmlns:x="adobe:ns:meta/">
      <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
        <rdf:Description rdf:about="">
          <Iptc4xmpExt:ImageRegion>
            <rdf:Bag>
              <rdf:li rdf:parseType="Resource">
                <Iptc4xmpExt:Name>
                  <rdf:Alt>
                    <rdf:li xml:lang="x-default">Face</rdf:li>
                    <rdf:li xml:lang="de">Gesicht</rdf:li>
                  </rdf:Alt>
                </Iptc4xmpExt:Name>
                <Iptc4xmpExt:RegionBoundary rdf:parseType="Resource">
                  <Iptc4xmpExt:rbShape>polygon</Iptc4xmpExt:rbShape>
                  <Iptc4xmpExt:rbUnit>relative</Iptc4xmpExt:rbUnit>
                  <Iptc4xmpExt:rbVertices>
                    <rdf:Seq>
                      <rdf:li rdf:parseType="Resource">
                        <Iptc4xmpExt:rbX>0.1</Iptc4xmpExt:rbX>
                        <Iptc4xmpExt:rbY>0.1</Iptc4xmpExt:rbY>
                      </rdf:li>
                      <rdf:li rdf:parseType="Resource">
                        <Iptc4xmpExt:rbX>0.4</Iptc4xmpExt:rbX>
                        <Iptc4xmpExt:rbY>0.1</Iptc4xmpExt:rbY>
                      </rdf:li>
                      <rdf:li rdf:parseType="Resource">
                        <Iptc4xmpExt:rbX>0.1</Iptc4xmpExt:rbX>
                        <Iptc4xmpExt:rbY>0.4</Iptc4xmpExt:rbY>
                      </rdf:li>
                    </rdf:Seq>
                  </Iptc4xmpExt:rbVertices>
                </Iptc4xmpExt:RegionBoundary>
              </rdf:li>
            </rdf:Bag>
          </Iptc4xmpExt:ImageRegion>
        </rdf:Description>
      </rdf:RDF>
    </x:xmpmeta>
    """

    metadata = parse_xmp(xmp)

    assert metadata["imageRegion"][0]["name"] == {"x-default": "Face", "de": "Gesicht"}


def test_parses_xmp_region_extra_metadata_to_stable_keys():
    xmp = """
    <x:xmpmeta xmlns:x="adobe:ns:meta/">
      <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
               xmlns:dc="http://purl.org/dc/elements/1.1/"
               xmlns:xmp="http://ns.adobe.com/xap/1.0/">
        <rdf:Description rdf:about="">
          <Iptc4xmpExt:ImageRegion>
            <rdf:Bag>
              <rdf:li rdf:parseType="Resource">
                <dc:description>
                  <rdf:Alt>
                    <rdf:li xml:lang="x-default">Description</rdf:li>
                    <rdf:li xml:lang="de">Beschreibung</rdf:li>
                  </rdf:Alt>
                </dc:description>
                <Iptc4xmpExt:Contributor>
                  <rdf:Bag>
                    <rdf:li rdf:parseType="Resource">
                      <Iptc4xmpExt:Name>Person Name</Iptc4xmpExt:Name>
                      <xmp:Identifier>
                        <rdf:Bag>
                          <rdf:li>https://example.org/person/1</rdf:li>
                        </rdf:Bag>
                      </xmp:Identifier>
                      <Iptc4xmpExt:Role>
                        <rdf:Bag>
                          <rdf:li>https://example.org/role/describer</rdf:li>
                        </rdf:Bag>
                      </Iptc4xmpExt:Role>
                    </rdf:li>
                  </rdf:Bag>
                </Iptc4xmpExt:Contributor>
              </rdf:li>
            </rdf:Bag>
          </Iptc4xmpExt:ImageRegion>
        </rdf:Description>
      </rdf:RDF>
    </x:xmpmeta>
    """

    metadata = parse_xmp(xmp)
    region = metadata["imageRegion"][0]

    assert region["XMP-dc:Description"] == {"x-default": "Description", "de": "Beschreibung"}
    assert region["XMP-iptcExt:Contributor"] == [
        {
            "name": "Person Name",
            "identifiers": ["https://example.org/person/1"],
            "role": ["https://example.org/role/describer"],
        }
    ]
