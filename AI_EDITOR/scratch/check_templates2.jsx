var comp = app.project.items.addComp('Test', 1920, 1080, 1.0, 10.0, 30.0);
var rqItem = app.project.renderQueue.items.add(comp);
var rqModule = rqItem.outputModule(1);
var templates = [];
for (var i = 0; i < rqModule.templates.length; i++) {
    templates.push(rqModule.templates[i]);
}
var f = new File('C:/Users/L.Thirumala Teja/AI_EDITOR/scratch/templates.txt');
f.open('w');
f.write(templates.join(', '));
f.close();
