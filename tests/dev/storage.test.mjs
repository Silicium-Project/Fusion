import test from 'node:test';
import assert from 'node:assert/strict';
import { remainingBudget, requireCoverage } from '../../tools/ci/storage-budget.mjs';
test('temporary storage has a hard ceiling and invalid usage fails closed',()=>{
 assert.equal(remainingBudget(100,50,400),250);
 for(const [a,b]of [[400,1],[399,1],[-1,10],[NaN,1],[1,Infinity]])assert.throws(()=>remainingBudget(a,b,400));
});
test('an App restricted to selected repositories cannot measure the organization budget',()=>{
 const installation={repository_selection:'all',account:{login:'Silicium-Project'}};
 const repos=[{id:1,private:true,owner:{login:'Silicium-Project'}}];
 const organization={total_private_repos:1,public_repos:0};
 assert.doesNotThrow(()=>requireCoverage(installation,organization,repos));
 assert.throws(()=>requireCoverage({...installation,repository_selection:'selected'},organization,repos));
 assert.throws(()=>requireCoverage(installation,{...organization,total_private_repos:2},repos));
 assert.throws(()=>requireCoverage(installation,organization,[]));
 assert.throws(()=>requireCoverage({...installation,suspended_at:'2026-10-25'},organization,repos));
});
