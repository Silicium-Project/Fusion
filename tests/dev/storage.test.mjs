import test from 'node:test';
import assert from 'node:assert/strict';
import { remainingBudget } from '../../tools/ci/storage-budget.mjs';
test('temporary storage has a hard ceiling and invalid usage fails closed',()=>{
 assert.equal(remainingBudget(100,50,400),250);
 for(const [a,b]of [[400,1],[399,1],[-1,10],[NaN,1],[1,Infinity]])assert.throws(()=>remainingBudget(a,b,400));
});
