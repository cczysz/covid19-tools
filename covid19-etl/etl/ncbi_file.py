import os
from pathlib import Path
import json
import re
import gzip
import subprocess
import shlex
from contextlib import closing
import asyncio

from etl import base
from helper.file_helper import FileHelper
from helper.metadata_helper import MetadataHelper

from botocore import UNSIGNED
from botocore.config import Config
import boto3
import codecs


DATA_PATH = os.path.dirname(os.path.abspath(__file__))


class NCBI_FILE(base.BaseETL):
    def __init__(self, base_url, access_token, s3_bucket):
        super().__init__(base_url, access_token, s3_bucket)

        self.program_name = "open"
        self.project_code = "NCBI"

        self.latest_srr_number = "SRR0"
        self.latest_drr_number = "DRR0"
        self.latest_err_number = "ERR0"

        self.file_helper = FileHelper(
            base_url=self.base_url,
            program_name=self.program_name,
            project_code=self.project_code,
            access_token=access_token,
        )

        self.metadata_helper = MetadataHelper(
            base_url=self.base_url,
            program_name=self.program_name,
            project_code=self.project_code,
            access_token=access_token,
        )

    def process(self, node_name, ext, bucket, key, excluded_set, headers=None):
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(
                self.stream_object_from_s3(
                    node_name, ext, bucket, key, excluded_set, headers
                )
            )
        finally:
            loop.close()

    def get_existed_accession_numbers(self, node_name):
        query_string = "{ " + node_name + " (first:0) { submitter_id } }"
        response = self.metadata_helper.query_node_data(query_string)
        if response.status_code != 200:
            raise Exception(
                f"ERROR: can not get a list of accession numbers of the node {node_name}"
            )
        records = response.json()["data"][node_name]
        return records

    async def file_to_submissions(self, filepath):
        filename = os.path.basename(filepath)
        did, rev, md5, size = self.file_helper.find_by_name(filename)
        if not did:
            guid = self.file_helper.upload_file(filepath)
            print(f"file {filepath.name} uploaded with guid: {guid}")
        else:
            print(f"file {filepath.name} exists in indexd... skipping...")
        os.remove(filepath)

    async def process_line(
        self, line, node_name, ext, headers, accession_number, n_rows, f, excluded_set
    ):
        r1 = re.findall("[SDE]RR\d+", line)
        if len(r1) == 0 and n_rows == 0:
            return f, accession_number
        assert (
            len(r1) == 1
        ), "The files have changed (expected {} contains accession number in the format of [SDE]RR\d+). We may need to update the ETL code".format(
            line
        )
        read_accession_number = r1[0]

        if read_accession_number in excluded_set:
            return f, accession_number

        if not accession_number or int(read_accession_number[3:]) != int(
            accession_number[3:]
        ):
            if f:
                f.close()
                asyncio.create_task(
                    self.file_to_submissions(
                        f"{DATA_PATH}/{node_name}_{accession_number}.{ext}"
                    )
                )
            accession_number = read_accession_number
            f = open(f"{DATA_PATH}/{node_name}_{accession_number}.{ext}", "w")
            if headers:
                f.write(headers)
        f.write(line)
        return f, accession_number

    async def stream_object_from_s3(
        self, node_name, ext, bucket, key, excluded_set, headers=None
    ):
        s3 = boto3.resource("s3", config=Config(signature_version=UNSIGNED))
        s3_object = s3.Object(bucket, key)
        line_stream = codecs.getreader("utf-8")
        accession_number = None
        n_rows = 0
        f = None
        try:
            for line in line_stream(s3_object.get()["Body"]):
                f, accession_number = await self.process_line(
                    line,
                    node_name,
                    ext,
                    headers,
                    accession_number,
                    n_rows,
                    f,
                    excluded_set,
                )
        except Exception as e:
            # close the opening file
            if f:
                f.close()


class BLASTN_FILE(NCBI_FILE):
    def __init__(self, base_url, access_token, s3_bucket):
        super().__init__(base_url, access_token, s3_bucket)
        self.headers = "acc\tqacc\tstaxid\tsacc\tslen\tlength\tbitscore\tscore\tpident\tsskingdom\tevalue\tssciname\n"
        self.bucket = "sra-pub-sars-cov2-metadata-us-east-1"
        self.key = "blastn/blastn.tsv"
        self.ext = "tsv"
        self.node_name = "virus_sequence_blastn"

    def upload_and_index_the_file(self):
        lists = super().get_existed_accession_numbers(self.node_name)
        super().process_line(
            self.node_name, "tsv", self.bucket, self.key, set(lists), self.headers
        )


class PEPTIDE_FILE(NCBI_FILE):
    def __init__(self, base_url, access_token, s3_bucket):
        super().__init__(base_url, access_token, s3_bucket)
        self.bucket = "sra-pub-sars-cov2-metadata-us-east-1"
        self.key = "peptides/peptides.json"
        self.ext = "json"
        self.node_name = "virus_sequence_peptide"

    def upload_and_index_the_file(self):
        lists = super().get_existed_accession_numbers(self.node_name)
        super().process(
            self.node_name, "tsv", self.bucket, self.key, set(lists), self.headers
        )


class CONTIG_FILE(NCBI_FILE):
    def __init__(self, base_url, access_token, s3_bucket):
        super().__init__(base_url, access_token, s3_bucket)
        self.bucket = "sra-pub-sars-cov2-metadata-us-east-1"
        self.key = "contigs/contigs.json"
        self.ext = "json"
        self.node_name = "virus_sequence_contig"

    def upload_and_index_the_file(self):
        lists = super().get_existed_accession_numbers(self.node_name)
        super().process(self.node_name, "tsv", self.bucket, self.key, set(lists))


class HMMSEARCH_FILE(NCBI_FILE):
    def __init__(self, base_url, access_token, s3_bucket):
        super().__init__(base_url, access_token, s3_bucket)
        self.bucket = "sra-pub-sars-cov2-metadata-us-east-1"
        self.key = "hmmsearch_notc/hmmsearch_notc.json"
        self.ext = "json"
        self.node_name = "virus_sequence_hmmsearch"

    def upload_and_index_the_file(self):
        lists = super().get_existed_accession_numbers(self.node_name)
        super().process(self.node_name, "tsv", self.bucket, self.key, set(lists))


class SRA_TAXONOMY_FILE(NCBI_FILE):
    def __init__(self, base_url, access_token, s3_bucket):
        super().__init__(base_url, access_token, s3_bucket)
        self.bucket = "sra-pub-sars-cov2-metadata-us-east-1"
        self.key = "sra_taxonomy/coronaviridae_07_31_2020_000000000000.gz"
        self.node_name = "virus_sequence_run_taxonomy"

    def upload_and_index_the_file(self):
        s3 = boto3.resource("s3", config=Config(signature_version=UNSIGNED))
        s3_object = s3.Object(self.bucket, self.key)
        file_path = f"{DATA_PATH}/{self.node_name}.gz"
        s3_object.download_file(file_path)
        asyncio.run(super().file_to_submissions(Path(file_path)))