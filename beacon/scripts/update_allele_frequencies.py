import requests, sys
from pymongo import MongoClient
import os


def complement(sequence):
    complement = {'A': 'T', 'T': 'A', 'C': 'G', 'G': 'C'}
    return ''.join(complement[base] for base in sequence)


# function to query 1000 Genomes for allele frequency
def query_1000_genomes(chrom, start, end, ref, alt, type):
    server = "https://rest.ensembl.org"
    ext = f"/map/human/GRCh37/{chrom}:{start}..{end}:1/GRCh38?"
 
    r = requests.get(server + ext, headers={"Content-Type": "application/json"})
 
    if not r.ok:
        r.raise_for_status()
        sys.exit()

    decoded = r.json()
    mappings = decoded['mappings']
    mapped_data = mappings[0]['mapped']
    mapped_start = mapped_data['start']
    mapped_end = mapped_data['end']
    
    ex = f"/sequence/region/human/{chrom}:{mapped_start}-{mapped_start}?"
    re = requests.get(server + ex, headers={"Content-Type": "application/json"})
    j = re.json()
    check = j['seq']
    
    
    # construct the HGVS notation
    if type == 'INDEL':
        hgvs_notation = f"{chrom}:g.{mapped_start-(len(ref))}_{mapped_end-(len(ref))}del{complement(ref)}ins{complement(alt)}"
    elif check == complement(alt):
        hgvs_notation = f"{chrom}:g.{mapped_start}{complement(alt)}>{complement(ref)}"
    elif 'most_severe_consequence' in  mapped_data:
        if mapped_data['most_severe_consequence'] == 'downstream_gene_variant':
            hgvs_notation = f"{chrom}:g.{mapped_start}{complement(alt)}>{complement(ref)}"
    elif type == "SNP":
        hgvs_notation = f"{chrom}:g.{mapped_start}{complement(ref)}>{complement(alt)}"
    
    # construct the URL for Ensembl VEP
    url = f"https://rest.ensembl.org/vep/human/hgvs/{hgvs_notation}?"
 
    # make GET request to the API
    response = requests.get(url, headers={"Content-Type": "application/json"})
 
    # see if request was successful
    if response.status_code == 200:
        json_response = response.json()
        print(f"GRCh38 + {hgvs_notation}")
        return json_response
    else:
        print(f"Bad request for variant {chrom}-{start}-{ref}-{alt}: {response.text}")
        return None
    
    
# connect to MongoDB
database_password = os.getenv('DB_PASSWD')
client = MongoClient(
    "mongodb://{}:{}@{}:{}/{}?authSource={}".format(
        "root",
        database_password,
        "db",
        27017,
        "beacon",
        "admin"
    )
)


collection = client.beacon.get_collection('genomicVariations')


# iterate over all variants, format them, query 1000 Genomes, and update the database
for variant in collection.find():
    chromosome = variant["_position"]["refseqId"]
    start_position = variant["_position"]["startInteger"]
    end_position = variant["_position"]["endInteger"]
    reference_base = variant["variation"]["referenceBases"]
    alternate_base = variant["variation"]["alternateBases"]
    variant_type = variant["variation"]['variantType']
    beacon_allele_frequency = len(variant["caseLevelData"])
    
    formatted_variant = f"{chromosome}-{start_position}-{end_position}-{reference_base}-{alternate_base}"
    print("------------------------------------")
    print(f"Variant + {formatted_variant}")
    try:
        # query 1000 Genomes for allele frequency
        allele_frequency = query_1000_genomes(chromosome, start_position, end_position, reference_base, alternate_base, variant_type)
        
        if allele_frequency is not None:
            total_frequency = 0.0
            if "colocated_variants" in allele_frequency[0]:
                if "frequencies" in allele_frequency[0]['colocated_variants'][0]:
                    data = allele_frequency[0]['colocated_variants'][0]['frequencies']
                    for key in data:
                        if "gnomadg" in data[key] and "af" in data[key]:
                            total_frequency = data[key]["af"]
                        elif "gnomadg" in data[key] and not "af" in data[key]:
                            total_frequency = data[key]["gnomadg"]
                        elif "gnomadg" not in data[key] and "af" in data[key]:
                            total_frequency = data[key]["af"]
                        else:
                            total_frequency = 1/collection.count_documents({}) # allele frequency in the beacon database
                        if total_frequency == 0:
                            total_frequency = 1/collection.count_documents({}) # allele frequency in the beacon database
                    collection.update_one(
                        {"variantInternalId": variant["variantInternalId"]},
                        {"$set": {"alleleFrequency": total_frequency}}
                    )
                else:
                    total_frequency = beacon_allele_frequency/client.beacon.get_collection('individuals').count_documents({}) # allele frequency in the beacon database
                    collection.update_one(
                        {"variantInternalId": variant["variantInternalId"]},
                        {"$set": {"alleleFrequency": total_frequency}}
                    )
            else:
                total_frequency = beacon_allele_frequency/client.beacon.get_collection('individuals').count_documents({}) # allele frequency in the beacon database
                collection.update_one(
                    {"variantInternalId": variant["variantInternalId"]},
                    {"$set": {"alleleFrequency": total_frequency}}
                )
            print(f"Updated variant {formatted_variant} with allele frequency {total_frequency}")
            
        else:
           print(f"Failed to retrieve allele frequency for {formatted_variant}")
           
    except ValueError as e:
        print(str(e))
        continue
    
    except Exception as e:
        
        print(f"Failed to process variant {formatted_variant}: {e}")
        continue
    
print("Finished updating allele frequencies.")