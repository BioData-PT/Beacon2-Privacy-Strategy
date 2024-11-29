	for collection in analyses biosamples individuals runs cohorts datasets genomicVariations budget history
  do
    mongoimport --jsonArray \
    --uri "mongodb://root:${DB_PASSWD}@127.0.0.1:27017/beacon?authSource=admin" \
		--file input_data/cineca_with_datasetid/${collection}.json --collection ${collection} ;
	done
