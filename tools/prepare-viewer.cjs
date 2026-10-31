const fs=require('node:fs'),path=require('node:path');
const output=path.resolve(__dirname,'../assets/models');
const base=path.join(__dirname,'node_modules/three'),vendor=path.join(output,'vendor');
fs.mkdirSync(vendor,{recursive:true});
for(const name of ['three.module.js','three.core.js'])fs.copyFileSync(path.join(base,'build',name),path.join(vendor,name));
const copied=new Set();
function copy(relative){
 if(copied.has(relative))return;copied.add(relative);
 const source=path.join(base,'examples/jsm',relative),target=path.join(vendor,'addons',relative);
 fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(source,target);
 for(const match of fs.readFileSync(source,'utf8').matchAll(/from\s+['"](\.[^'"]+)['"]/g))copy(path.normalize(path.join(path.dirname(relative),match[1])));
}
copy('loaders/GLTFLoader.js');copy('controls/OrbitControls.js');
fs.copyFileSync(path.join(__dirname,'node_modules/fflate/esm/browser.js'),path.join(vendor,'fflate.js'));
fs.copyFileSync(path.join(base,'LICENSE'),path.join(vendor,'THREE-LICENSE.txt'));
fs.copyFileSync(path.join(__dirname,'node_modules/fflate/LICENSE'),path.join(vendor,'FFLATE-LICENSE.txt'));
fs.copyFileSync(path.join(__dirname,'viewer-25d.html'),path.join(output,'index.html'));
console.log('Viewer prepared:',output);
