"""Run isolated local regressions and persist truthful machine-readable results."""
from pathlib import Path
import argparse, sys, unittest, json, time, platform, io, importlib.metadata
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'third_party'))
from bridge import __version__
class Recorded(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.entries=[]
    def addSuccess(self,t):super().addSuccess(t);self.entries.append({'test':t.id(),'status':'passed'})
    def addFailure(self,t,e):super().addFailure(t,e);self.entries.append({'test':t.id(),'status':'failed','detail':self._exc_info_to_string(e,t)})
    def addError(self,t,e):super().addError(t,e);self.entries.append({'test':t.id(),'status':'error','detail':self._exc_info_to_string(e,t)})
    def addSkip(self,t,r):super().addSkip(t,r);self.entries.append({'test':t.id(),'status':'skipped','reason':r})
class Tee:
    def __init__(self):self.buf=io.StringIO()
    def write(self,text):sys.stdout.write(text);self.buf.write(text)
    def flush(self):sys.stdout.flush()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir',type=Path,default=ROOT/'reports'/'current')
    args=parser.parse_args()
    report=args.report_dir;report.mkdir(parents=True,exist_ok=True)
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    out=Tee();start=time.time()
    result=unittest.TextTestRunner(stream=out,verbosity=2,resultclass=Recorded).run(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py'))
    try:pdf=importlib.metadata.version('pypdf')
    except importlib.metadata.PackageNotFoundError:pdf='not installed'
    data={'version':__version__,'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'python':sys.version,'platform':platform.platform(),'pypdf_test_version':pdf,'duration_seconds':round(time.time()-start,3),'tests':result.testsRun,'passed':sum(x['status']=='passed' for x in result.entries),'failed':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'success':result.wasSuccessful(),'scope':'Isolated local tests. No authenticated OpenAI control-plane, user account or personal files; synthetic Office components and installer mocks are explicitly used.','cases':result.entries}
    (report/'local-tests.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');(report/'local-tests.txt').write_text(out.buf.getvalue(),encoding='utf-8')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
