const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {validateReview,visibleCase} = require('../scripts/review_assets/review.js');

test('review export/import preserves ratings and literal notes for the exact run', () => {
  const payload={version:1,run_id:'run',reviews:{a:{rating:'needs-work',notes:'<script>not executable</script>'}}};
  const result=validateReview(JSON.parse(JSON.stringify(payload)),'run',['a']);
  assert.equal(result.a.notes,payload.reviews.a.notes);
  assert.equal(result.a.rating,'needs-work');
  assert.equal(Object.getPrototypeOf(result),null);
});
test('rejects wrong-run, unknown-case, oversized-note and invalid-rating imports', () => {
  const valid={version:1,run_id:'run',reviews:{a:{rating:'acceptable',notes:''}}};
  assert.throws(()=>validateReview(valid,'other',['a']));
  assert.throws(()=>validateReview(valid,'run',['b']));
  for (const entry of [{rating:'official-winner',notes:''},{rating:'acceptable',notes:'x'.repeat(10001)}]) {
    assert.throws(()=>validateReview({...valid,reviews:{a:entry}},'run',['a']));
  }
  assert.throws(()=>validateReview({...valid,reviews:[]},'run',['a']));
});
test('family/status/review filters are independent of aesthetic approval', () => {
  const item={family:'dense',status:'review'};
  assert.equal(visibleCase(item,null,'all','flagged'),true);
  assert.equal(visibleCase(item,null,'other','all'),false);
  assert.equal(visibleCase(item,null,'all','failed'),false);
  assert.equal(visibleCase(item,{rating:'unusable'},'all','unreviewed'),false);
  assert.equal(visibleCase({...item,status:'checks-passed'},null,'all','unreviewed'),true);
});

function reviewPage(storageFails) {
  const nodes = new Map(), stored = [];
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {textContent:'', value:'all', listeners:{},
      addEventListener(type, fn) { this.listeners[type] = fn; }});
    return nodes.get(id);
  }
  node('review-data').textContent = JSON.stringify({run_id:'run', cases:[
    {id:'a', family:'family', status:'checks-passed'}]});
  const card = {...node('card'), dataset:{case:'a'}, querySelector:node};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../scripts/review_assets/review.js'), 'utf8'), {
    document:{getElementById:node, querySelectorAll:() => [card]},
    localStorage:{getItem:() => null, setItem(key, value) {
      if (storageFails) throw new Error('quota exceeded');
      stored.push(JSON.parse(value));
    }},
  });
  return {node, stored};
}

test('import keeps notes usable and preserves a failed-storage warning', async () => {
  const {node, stored} = reviewPage(true);
  const payload = {version:1, run_id:'run', reviews:{a:{rating:'needs-work', notes:'Small text'}}};
  const target = {files:[{size:100, text:async () => JSON.stringify(payload)}], value:'selected'};
  await node('import').listeners.change({target});
  assert.match(node('storage-status').textContent, /storage unavailable/i);
  assert.match(node('storage-status').textContent, /export/i);
  assert.equal(node('.notes').value, 'Small text');
  assert.equal(node('.rating').value, 'needs-work');
  assert.equal(stored.length, 0);
  assert.equal(target.value, '');
});

test('successful import confirms persistence for the exact run', async () => {
  const {node, stored} = reviewPage(false);
  const payload = {version:1, run_id:'run', reviews:{a:{rating:'acceptable', notes:'Readable'}}};
  await node('import').listeners.change({target:{
    files:[{size:100, text:async () => JSON.stringify(payload)}], value:'selected'}});
  assert.match(node('storage-status').textContent, /Imported notes/);
  assert.deepEqual(stored, [payload]);
  assert.equal(node('.notes').value, 'Readable');
});
