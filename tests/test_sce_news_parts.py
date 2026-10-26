import json
from pathlib import Path
import sys

import pytest
from scripts import run_sce_news_parts as runner


def setup(tmp_path,monkeypatch,statuses):
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    inputs=tmp_path/'inputs';inputs.mkdir();out=tmp_path/'calls'
    (inputs/'summary.json').write_text(json.dumps({'proposed_total_cap_usd':.5,
        'parts':[{'part':i,'folder':f'inputs/part_{i}','package_cap_usd':.25} for i in (1,2)]}))
    attempts=[]
    def fake(argv):
        if '--execute' not in argv:return
        attempts.append(argv[argv.index('--inputs')+1])
        folder=Path(argv[argv.index('--out')+1]);folder.mkdir(parents=True)
        (folder/'state.json').write_text(json.dumps({'status':statuses[len(attempts)-1],'spent_or_reserved_upper_usd':.01}))
    monkeypatch.setattr(runner.base,'main',fake)
    monkeypatch.setattr(sys,'argv',['runner','--inputs',str(inputs),'--out',str(out),'--execute','--authorization-note','Approved test scope'])
    return out,attempts


def test_incomplete_first_part_stops_without_resending(tmp_path,monkeypatch):
    out,attempts=setup(tmp_path,monkeypatch,['stopped_on_error'])
    runner.main()
    assert len(attempts)==1
    assert json.loads((out/'chain_receipt.json').read_text())['status']=='stopped_no_retry'


def test_completed_parts_are_sequentially_automatic(tmp_path,monkeypatch):
    out,attempts=setup(tmp_path,monkeypatch,['completed','completed'])
    runner.main()
    assert len(attempts)==2
    receipt=json.loads((out/'chain_receipt.json').read_text())
    assert receipt['status']=='completed' and receipt['reported_or_reserved_usd']==pytest.approx(.02)


def test_no_authorization_never_dispatches(tmp_path,monkeypatch):
    out,attempts=setup(tmp_path,monkeypatch,['completed'])
    monkeypatch.setattr(sys,'argv',sys.argv[:-2])
    with pytest.raises(ValueError,match='authorization'):runner.main()
    assert attempts==[] and not out.exists()
