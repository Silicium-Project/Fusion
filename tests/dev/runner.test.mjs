import test from 'node:test';
import assert from 'node:assert/strict';
import { countTests } from '../../tools/lib/runner.mjs';
import { parseArgs, inside } from '../../tools/lib/process.mjs';
for(const [format,output,count] of [
 ['node','# tests 4',4],['vitest','Tests  12 passed (12)',12],['rust','test result: ok. 9 passed; 0 failed;\ntest result: ok. 3 passed;',12],['go','{"Action":"pass","Test":"TestOne"}\n{"Action":"pass","Package":"api"}',1],['anchor','53 passing (5m)',53],['pytest','19 passed in 2.14s',19],['playwright','  6 passed (1.2s)',6],
])test(`${format} reports executed tests`,()=>assert.equal(countTests(output,format),count));
test('unrecognized or empty output is never a test pass',()=>assert.equal(countTests('passed','node'),0));
test('arguments remain data and duplicate options fail',()=>{assert.deepEqual(parseArgs(['ci','plan','--base','$(id)','--json']).options,{base:'$(id)',json:true});assert.throws(()=>parseArgs(['--base','a','--base','b']));});
test('file boundaries reject escaping paths',()=>assert.throws(()=>inside('../wallet')));
