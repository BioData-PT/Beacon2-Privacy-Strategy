# Script to load the db using backups

natureData=../../natureDataFiles
#metadataDir=$natureData/april2023
#genomicDataDir=$natureData/april2023
#backupDir=/home/ubuntu/beacon/dumps
backupDir=$natureData/april2023

#metadataDir=data/mydata/cineca
#genomicDataDir=data/mydata/cineca

DB_PASSWD="example"
source .env # import db passwd

mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/analyses*.bson --collection analyses
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/biosamples*.bson --collection biosamples
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/cohorts*.bson --collection cohorts
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/datasets*.bson --collection datasets
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/individuals*.bson --collection individuals
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/runs*.bson --collection runs
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/budget*.bson --collection budget
mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/history*.bson --collection history

mongorestore --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $backupDir/genomicVariations*.bson --collection genomicVariations
#mongoimport --jsonArray --uri "mongodb://root:$DB_PASSWD@127.0.0.1:27017/beacon?authSource=admin" $genomicDataDir/genomicVariations*.json.gz --collection genomicVariations

