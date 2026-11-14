Raw data root (git-ignored). Layout: `<experiment>/sensors/pod=NN/date=YYYY-MM-DD/part-*.parquet`,
`<experiment>/images/Pnn/YYYYMMDD/<image_id>.png`. Files are written once, read-only. Never edit
or delete raw files; corrections are made through calibration records and QC flags.
