"""Execute the forward notebook in a fresh in-process IPython session.

Avoid Windows subprocess kernel-launch stalls; preserve streams and rich output.
Run this script as a fresh Python process from the repository root.
"""
from pathlib import Path
import os
os.environ["IPYTHONDIR"] = str(Path("data/processed/test_tmp/ipython").resolve())
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"
import nbformat
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output

path=Path('notebooks/07_forward_threat_calibration.ipynb')
nb=nbformat.read(path,as_version=4)
shell=InteractiveShell.instance()
try:
    count=0
    for cell in nb.cells:
        if cell.cell_type!='code': continue
        count+=1
        print(f'Executing cell {count}',flush=True)
        with capture_output() as captured:
            result=shell.run_cell(cell.source,store_history=True,silent=False)
        outputs=[]
        if captured.stdout: outputs.append(nbformat.v4.new_output('stream',name='stdout',text=captured.stdout))
        if captured.stderr: outputs.append(nbformat.v4.new_output('stream',name='stderr',text=captured.stderr))
        for item in captured.outputs:
            outputs.append(nbformat.v4.new_output('display_data',data=item.data,metadata=item.metadata))
        if result.result is not None:
            data,metadata=shell.display_formatter.format(result.result)
            outputs.append(nbformat.v4.new_output('execute_result',data=data,metadata=metadata,execution_count=count))
        cell.execution_count=count
        cell.outputs=outputs
        if result.error_before_exec or result.error_in_exec:
            raise RuntimeError(f'Notebook cell {count} failed') from (result.error_before_exec or result.error_in_exec)
    nbformat.write(nb,path)
    print('Executed and saved notebook',flush=True)
finally:
    InteractiveShell.clear_instance()
