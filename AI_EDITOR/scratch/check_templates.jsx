var comp = app.project.items.addComp('Test', 1920, 1080, 1.0, 10.0, 30.0);
var rqItem = app.project.renderQueue.items.add(comp);
var rqModule = rqItem.outputModule(1);
var templates = [];
for (var i = 0; i < rqModule.templates.length; i++) {
    templates.push(rqModule.templates[i]);
}
alert(templates.join(', '));
