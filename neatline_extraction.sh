#! /bin/bash

geopdf=$1
DPI=150

neatline=$(gdalinfo $geopdf 2> /dev/null | grep 'NEATLINE' | sed 's/NEATLINE=//' | sed 's/^ *//' | sed 's/ *$//')
utm_zone=$(gdalinfo $geopdf 2> /dev/null | grep 'UTM Zone' | sed 's/.*UTM Zone \([0-9][0-9]*\).*/\1/')

echo '"id","WKT"' > ${geopdf%.*}_cutline.csv
echo "\"1\",\"$neatline\"" >> ${geopdf%.*}_cutline.csv

rm NEATLINE.csv
ln -s ${geopdf%.*}_cutline.csv NEATLINE.csv

if [ $utm_zone -eq '10' ]
then
    vrt=neatline_utm10n.vrt
else
    vrt=neatline_utm11n.vrt
fi

gdalwarp -cutline $vrt -cl NEATLINE -crop_to_cutline ${geopdf} ${geopdf%.*}_${DPI}dpi.tif \
    -dstnodata 0 \
    -t_srs EPSG:26911 \
    --config GDAL_PDF_LAYERS "all" \
    --config GDAL_PDF_LAYERS_OFF "Images,Map_Frame.PLSS" \
    --config GDAL_PDF_BANDS 3 \
    --config GDAL_PDF_DPI $DPI

rm -f ${geopdf%.*}_ycbcr_${DPI}dpi.tif
gdal_translate -co COMPRESS=JPEG -co PHOTOMETRIC=YCBCR \
    -co TILED=YES \
    ${geopdf%.*}_${DPI}dpi.tif ${geopdf%.*}_ycbcr_${DPI}dpi.tif

rm ${geopdf%.*}_${DPI}dpi.tif

rm -f ${geopdf%.*}_ycbcr.tif_${DPI}dpi.ovr
gdaladdo -ro ${geopdf%.*}_ycbcr_${DPI}dpi.tif 4 8 16 32 64 128 256 \
    --config COMPRESS_OVERVIEW JPEG \
    --config PHOTOMETRIC_OVERVIEW YCBCR \
    --config INTERLEAVE_OVERVIEW PIXEL
