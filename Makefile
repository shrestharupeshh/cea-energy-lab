.PHONY: test calc cad pcb sim dashboard
test:
	make -C firmware/node/test_host test
	pytest
calc:
	python -m plantpulse.engineering.report
	python scripts/build_bom.py
cad:
	python hardware/mechanical/cad/build_all.py
pcb:
	cd hardware/electrical/pcb && python3 generate_pcb.py && python3 export_fab.py && python3 generate_schematic.py
sim:
	python simulation/run_virtual_study.py
dashboard:
	streamlit run software/plantpulse/dashboard/app.py
