#! /usr/bin/env python
# vim: set fileencoding=utf-8 :
from __future__ import print_function
from __future__ import unicode_literals
usage = """\
Generate clipping polygons from the coordinates on a set of adjoining 7.5
minute USGS quad maps.

The input is a specially crafted text file containing the upper left coordinate
(lat,lon in NAD83, decimal degrees) followed by lines indicating the USGS quad
names separated by whitespace and | characters.  The last line contains the
lower right coordinate of the right-most quad.  The text file must be in the
same location as the GeoPDF files so the script can determine the projection of
the PDF.

The output is a csv file containing ID, quad name, and the cutline polygon
definition (as text), suitable for clipping with GDAL.
"""
import argparse
import sys
import re
import os
import logging
import subprocess
from pathlib import Path

import psycopg2
import psycopg2.extras

from osgeo import gdal, osr

parser = argparse.ArgumentParser(
    description=usage,
    formatter_class=argparse.RawDescriptionHelpFormatter)
group = parser.add_mutually_exclusive_group()
group.add_argument("-v", "--verbose", action="store_true", dest="verbose",
                   default=True, help="be more verbose")
group.add_argument("-q", "--quiet", action="store_false", dest="verbose",
                   default=True, help="be quiet")
parser.add_argument("textmap", help="textmap file")
parser.add_argument("outfile", nargs="?", type=argparse.FileType('w'),
                    default=sys.stdout)

args = parser.parse_args()

if args.verbose:
    logger = logging.getLogger('root')
    logger.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
    console.setFormatter(formatter)
    logger.addHandler(console)

def get_srid(geopdf):
    ds = gdal.Open(geopdf)
    # neatline_wkt = ds.GetMetadataItem("NEATLINE")
    try:
        projection = ds.GetProjectionRef()
        srs = osr.SpatialReference()
        srs.ImportFromWkt(projection)
        ds = None
        if srs.IsProjected():
            srid = srs.GetAuthorityCode("PROJCS")
        else:
            srid = srs.GetAuthorityCode("GEOGCS")
    except:
        # GeoPDF is stupid, and so is python gdal
        srids = {'NAD83 / UTM zone 11N': 26911,
                'UTM Zone 11, Northern Hemisphere': 26911,
                'NAD83 / UTM zone 10N': 26910,
                'UTM Zone 10, Northern Hemisphere': 26910}
        gdalinfo = subprocess.check_output(["gdalinfo", geopdf], universal_newlines=True)
        proj_descrip = None
        for line in gdalinfo.split('\n'):
            if 'PROJCS' in line:
                proj_descrip = re.sub('.*"([^"]+)".*', r'\1', line)
                print(proj_descrip)
        # Now stupidly match
        if proj_descrip in srids:
            srid = srids[proj_descrip]
        else:
            srid = None

    return srid

def get_corners(lats, lons, row, col):
    """ returns the five coordinates (first coordinate repeated) from the
        lats and lons arrays based on the row and col where 0, 0 is the
        upper left """

    ul = (lons[col], lats[row])
    ur = (lons[col+1], lats[row])
    lr = (lons[col+1], lats[row+1])
    ll = (lons[col], lats[row+1])

    return (ul, ur, lr, ll, ul)

def get_cutline(corners, srid, cursor):
    corners_astext = ','.join([' '.join((str(x[0]), str(x[1])))
                            for x in corners])
    linestring_text = "LINESTRING({c})".format(c=corners_astext)

    query = "SELECT ST_AsText(ST_MakePolygon(ST_Transform(ST_Segmentize(ST_SetSRID(ST_GeomFromText(%s), 4269), 0.01), %s)));"
    params = (linestring_text, srid)
    cursor.execute(query, params)
    if cursor.rowcount:
        cutline = next(cursor)[0]
    else:
        cutline = None

    return cutline

def parse_coords(line):
    (coords, comments) = line.split(' ', 1)
    (lat, lon) = [float(x) for x in coords.split(',')]

    return (lat, lon)

def parse_quad_name_row(row):
    row = row.strip()
    quads = [x.strip() for x in row.split('|')]

    return quads

connection = psycopg2.connect(
    host='example.com', database='postgis', user='USERNAME',
    port=5432,
    cursor_factory=psycopg2.extras.DictCursor,
    application_name='neatline_extraction')
cursor = connection.cursor()

# Read textmap into coordinates and quads
with open(args.textmap) as inf:
    ul_coords = next(inf)
    quad_rows = [x for x in inf]
    lr_coords = quad_rows[-1]
    quad_rows = quad_rows[:-1]

# Extract corners for all quads
(start_lat, start_lon) = parse_coords(ul_coords)
(end_lat, end_lon) = parse_coords(lr_coords)
offset = int(round(7.5/60.0*1000))
lats = [y/1000.0 for y in range(int(round(start_lat*1000)),
                                int(round(end_lat*1000)),
                                offset * -1)] + [end_lat]
lons = [x/1000.0 for x in range(int(round(start_lon*1000)),
                                int(round(end_lon*1000)),
                                offset)] + [end_lon]

# Get a list of GeoPDF quads
(basepath, textmap_filename) = os.path.split(args.textmap)
if basepath == '':
    basepath = '.'
p = Path(basepath)
pdf_files = [str(x) for x in p.glob('*.pdf')]

# Populate quads dictionary with cutline, srid
quads = {}
for row, quad_row in enumerate(quad_rows):
    quads[row] = {}
    quad_array = parse_quad_name_row(quad_row)
    for col, quad in enumerate(quad_array):
        quads[row][col] = {}
        quad_name = quad.replace(' ', '_')
        quads[row][col]['name'] = quad_name
        pdf_filename = None
        for pdf_file in pdf_files:
            if quad_name in pdf_file:
                quads[row][col]['pdf_name'] = pdf_file
                srid = get_srid(pdf_file)
                quads[row][col]['srid'] = srid
                pdf_filename = os.path.join(basepath, pdf_file)
        if srid is not None and pdf_filename is not None:
            cutline = get_cutline(get_corners(lats, lons, row, col),
                                  srid, cursor)
            quads[row][col]['cutline'] = cutline
            cutline_filename = pdf_filename[:-4] + "_cutline.csv"
            logger.info("writing {f}".format(f=cutline_filename))
            with open(cutline_filename, 'w') as of:
                of.write('"id","WKT"\n')
                of.write('"1","{c}"\n'.format(c=cutline))
        else:
            quads[row][col]['cutline'] = None
cursor.close()
connection.close()
