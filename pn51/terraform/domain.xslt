<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" omit-xml-declaration="yes"/>
  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>
  <xsl:template match="/domain/devices/disk[target/@dev='vda']">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()[not(self::backingStore)]"/>
      <backingStore type="file">
        <format type="qcow2"/>
        <source file="${base_image_path}"/>
        <backingStore/>
      </backingStore>
    </xsl:copy>
  </xsl:template>
  <xsl:template match="/domain/devices/disk[target/@dev='vda' or target/@dev='vdb']/@type">
    <xsl:attribute name="type">file</xsl:attribute>
  </xsl:template>
  <xsl:template match="/domain/devices/disk[target/@dev='vda']/source">
    <source file="${root_disk_path}"/>
  </xsl:template>
  <xsl:template match="/domain/devices/disk[target/@dev='vdb']/source">
    <source file="${data_disk_path}"/>
  </xsl:template>
  <xsl:template match="/domain/devices/graphics|/domain/devices/audio|/domain/devices/video"/>
</xsl:stylesheet>
