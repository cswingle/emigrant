#! /bin/bash
#
# Usage: ./neatline_extraction.sh geopdf dpi
#
# Note: you need a VRT for every projection in your input data (lines 20-25)
# and you need to set the output srs on line 6
# 2016-04-29: revise to use the cutlines generated using neatline_extraction.py
#
geopdf=$1
dpi=$2

OUTPUT_SRS="EPSG:26911"

# neatline=$(gdalinfo $geopdf 2> /dev/null | grep 'NEATLINE' | sed 's/NEATLINE=//' | sed 's/^ *//' | sed 's/ *$//')
utm_zone=$(gdalinfo $geopdf 2> /dev/null | grep 'UTM Zone' | sed 's/.*UTM Zone \([0-9][0-9]*\).*/\1/')

# echo '"id","WKT"' > ${geopdf%.*}_cutline.csv
# echo "\"1\",\"$neatline\"" >> ${geopdf%.*}_cutline.csv

rm NEATLINE.csv
ln -s ${geopdf%.*}_cutline.csv NEATLINE.csv

if [ $utm_zone -eq '10' ]
then
    vrt=neatline_utm10n.vrt
else
    vrt=neatline_utm11n.vrt
fi

gdalwarp -cutline $vrt -cl NEATLINE -crop_to_cutline ${geopdf} ${geopdf%.*}_${dpi}dpi.tif \
    -dstnodata 0 \
    -t_srs ${OUTPUT_SRS} \
    --config GDAL_PDF_LAYERS "all" \
    --config GDAL_PDF_LAYERS_OFF "Images,Map_Frame.PLSS" \
    --config GDAL_PDF_BANDS 3 \
    --config GDAL_PDF_dpi $dpi \
    -r cubicspline

rm -f ${geopdf%.*}_ycbcr_${dpi}dpi.tif
gdal_translate -co COMPRESS=JPEG -co PHOTOMETRIC=YCBCR \
    -co TILED=YES \
    ${geopdf%.*}_${dpi}dpi.tif ${geopdf%.*}_ycbcr_${dpi}dpi.tif

rm ${geopdf%.*}_${dpi}dpi.tif

rm -f ${geopdf%.*}_ycbcr.tif_${dpi}dpi.ovr
gdaladdo -ro ${geopdf%.*}_ycbcr_${dpi}dpi.tif 4 8 16 32 64 128 256 \
    --config COMPRESS_OVERVIEW JPEG \
    --config PHOTOMETRIC_OVERVIEW YCBCR \
    --config INTERLEAVE_OVERVIEW PIXEL
