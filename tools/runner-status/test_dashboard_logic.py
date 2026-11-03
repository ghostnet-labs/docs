"""Exercise the actual browser helper functions with Node, without a browser."""
import os
import shutil
import subprocess
import unittest

import runner_status as rs


class DashboardLogicTest(unittest.TestCase):
    def test_investigation_logic(self):
        node = os.environ.get("RUNNER_STATUS_NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node is needed for browser logic tests")
        subprocess.run([node, "--check"], input=rs.PAGE_JS, text=True, check=True)
        helpers = rs.PAGE_JS.split("/* ---- on-demand investigation:", 1)[1]
        helpers = helpers.split("*/", 1)[1].split("const COMMANDS=", 1)[0]
        helpers += next(line for line in rs.PAGE_JS.splitlines()
                        if line.startswith("function rows(")) + "\n"
        helpers += next(line for line in rs.PAGE_JS.splitlines()
                        if line.startswith("function renderCommands(")) + "\n"
        helpers += next(line for line in rs.PAGE_JS.splitlines()
                        if line.startswith("const esc=")) + "\n"
        helpers += next(line for line in rs.PAGE_JS.splitlines()
                        if line.startswith("const url=")) + "\n"
        prelude = r'''
const assert=require('node:assert/strict');
const localStorage={getItem:()=>null};
const arr=v=>Array.isArray(v)?v:[];
const pl=(n,w,p)=>n+' '+(n===1?w:(p||w+'s'));
let S=null,FLT='',QF='all';const PREF={sla:20};
let ORDER='age';const ordered=items=>items;
const nodes={};const $=id=>nodes[id]||(nodes[id]={});
const document={querySelectorAll:()=>[]};
const mount=(el,html)=>{el.innerHTML=html};
const dur=m=>m==null?'-':m+'m';const ic=()=>'<svg></svg>';
const prs=()=>'';const COMMANDS=[],SAVED=[];let CMD_SEL=0,PAUSED=false;
function flat(s){return s.machines.flatMap(m=>m.runners.map(r=>({r,m,vm:null})))}
'''
        cases = r'''
const runner=(name,status,labels)=>({name,status,labels});
S={machines:[{name:'Mac Studio',runners:[
 runner('linux-idle','idle',['self-hosted','Linux','ARM64']),
 runner('mac-busy','busy',['self-hosted','macOS','ARM64']),
 runner('linux-off','offline',['self-hosted','linux','x64'])]}],jobs:[]};
const j={repo:'firmware',workflow:'Build',name:'kernel',branch:'feature/one',
 labels:['self-hosted','linux','arm64'],prs:[{number:42}],status:'queued',age_min:30,url:'https://github.com/job/1'};
assert.equal(compatibleRunners(j).length,1);
assert.match(queueDiagnosis(j),/1 idle runner/);
assert.equal(compatibleRunners({...j,hosted:true}).length,0);
assert.match(queueDiagnosis({...j,hosted:true}),/Local runners cannot/);
assert.match(queueDiagnosis({...j,labels:[]}),/not reported/);
assert.match(queueDiagnosis({...j,labels:['gpu']}),/No local runner/);
assert.match(queueDiagnosis({...j,labels:['macOS']}),/1 busy runner/);
assert.match(queueDiagnosis({...j,labels:['x64']}),/offline/);
assert.match(queueDiagnosis({...j,status:'waiting'}),/approvals/);
const f=searchFields(j,{r:S.machines[0].runners[0],m:S.machines[0],vm:'gh-ubuntu'},'queued');
assert(smartMatch(f,'repo:firmware status:queued label:linux machine:"Mac Studio" -branch:main pr:42'));
assert(!smartMatch(f,'status:running'));
assert(!smartMatch(f,'-repo:firmware'));
assert(smartMatch(f,'kernel feature/one'));
assert(smartMatch(f,'vm:gh-ubuntu runner:linux'));
assert.notEqual(jobKey(j),jobKey({...j,url:'https://github.com/job/2'}));
S.jobs=[j,{...j,url:'https://github.com/job/2',age_min:10},
 {...j,url:'https://github.com/job/3',age_min:null}];
assert.equal(queueStats().median,20);
assert.equal(queueStats().oldest,30);
assert.equal(queueStats().breached,1);
S.machines[0].runners[0].job=j;
assert.equal(jobRecords().length,3); // runner jobs deduplicate by URL
delete S.machines[0].runners[0].job;
FLT='status:queued -branch:main';assert.equal(filteredRecords().length,3);
QF='running';assert.equal(filteredRecords().length,0);
QF='attention';assert.equal(filteredRecords().length,1);
assert.equal(csvCell('=SUM(1,2)'),"\"'=SUM(1,2)\"");
assert.equal(csvCell('say "yes"'),'"say ""yes"""');
assert(activityCSV().includes('Repository,')===false); // every cell quoted
assert(activityCSV().includes('"Age minutes"'));
assert.equal(jobStatusLabel('running'),'In progress');
assert.equal(jobStatusLabel('queued'),'Queued');
S.org='ghostnet-labs';
assert.equal(prPresentation({state:'open'}).state,'open');
assert.equal(prPresentation({state:'open',draft:true}).icon,'prDraft');
assert.equal(prPresentation({state:'merged',draft:true}).icon,'merge');
assert.equal(prPresentation({state:'closed',draft:true}).icon,'prClosed');
assert.equal(prPresentation({}).state,'unknown');
const prLink=prHTML({number:42,url:'https://github.com/o/r/pull/42',state:'merged',title:'Fix <script>'});
assert(prLink.includes('data-pr-state="merged"'));
assert(prLink.includes('>#42<'));
assert(!prLink.includes('PR #42'));
assert(prLink.includes('&lt;script&gt;'));
assert.equal(repoURL(j),'https://github.com/ghostnet-labs/firmware');
assert(branchHTML(j,'feature/a b').includes('/tree/feature%2Fa%20b'));
assert(branchHTML({...j,head_repo:'contributor/firmware'},'feature/pr').includes('github.com/contributor/firmware/tree/feature%2Fpr'));
assert(branchHTML(j,'x"><script>').includes('&lt;script&gt;'));
assert(commitHTML({...j,head_sha:'abcdef0123456789abcdef0123456789abcdef01'}).includes('>abcdef0<'));
assert.equal(commitHTML({...j,head_sha:'not-a-sha'}),'');
assert(commitHTML({...j,head_repo:'contributor/firmware',head_sha:'abcdef0123456789abcdef0123456789abcdef01'}).includes('github.com/contributor/firmware/commit/'));
assert(gitRefsHTML({...j,head_sha:'abcdef0123456789abcdef0123456789abcdef01'}).includes('git-branch'));
WATCH=[{key:jobKey(j),name:j.name,repo:j.repo}];
EXPLORE_TAB='watch';renderExplore();
assert(nodes.exploreBody.innerHTML.includes('Queued'));
INSPECT_KEY=jobKey(j);renderInspector();
assert(nodes.inspectBody.innerHTML.includes('status-badge queued'));
nodes['cmd-in']={value:'firmware'};renderCommands();
assert(nodes['cmd-list'].innerHTML.includes('firmware · Queued'));
S.jobs=[];assert.equal(queueStats().median,null);
const many=Array.from({length:31},(_,i)=>i);
const row=x=>'<li>'+x+'</li>';
assert.equal((rows(many,'wait',row).match(/<li>/g)||[]).length,12);
assert(rows(many,'wait',row).includes('Showing 12 of 31'));
ACT_LIMIT=24;assert(rows(many,'wait',row).includes('Showing 24 of 31'));
ACT_LIMIT=36;assert(rows(many,'wait',row).includes('Show fewer'));
assert.equal((rows(many,'work',row).match(/<li>/g)||[]).length,31);
console.log('Investigation helper assertions passed');
'''
        subprocess.run([node], input=prelude + helpers + cases, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
