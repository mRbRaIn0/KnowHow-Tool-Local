import { readdir, readFile } from 'node:fs/promises';
import { SourceTextModule } from 'node:vm';
async function check(folder) {
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const path = `${folder}/${entry.name}`;
    if (entry.isDirectory()) await check(path);
    else if (path.endsWith('.js')) new SourceTextModule(await readFile(path, 'utf8'), { identifier: path });
  }
}
await check('frontend/js');
console.log('All frontend modules parse successfully.');
