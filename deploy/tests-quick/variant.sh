curl \
 -H 'Content-Type: application/json' \
 -X POST \
 -d '{
  "meta": {
    "apiVersion": "2.0"
  },
  "query": {
    "requestParameters": {
  "alternateBases": "G" ,
  "referenceBases": "A" ,
"start": [ 16050074 ],
      "end": [ 16050568 ],
  "variantType": "SNP"
    },
    "filters": [],
    "includeResultsetResponses": "HIT",
    "pagination": {
      "skip": 0,
      "limit": 10
    },
    "testMode": false,
    "requestedGranularity": "record"
  }
}' \
 http://localhost:5050/api/g_variants/
