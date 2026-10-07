
var output = [];
try {
    app.newProject();
    var f = new File("C:/Users/L.Thirumala Teja/Downloads/fragment - slowed - slxughter.mp3");
    if (!f.exists) output.push("not found");
    var io = new ImportOptions(f);
    var item = app.project.importFile(io);
    output.push("Imported: " + item.name);
} catch (e) {
    output.push("Error: " + e.toString());
}
var out = new File("C:/Users/L.Thirumala Teja/AI_EDITOR/scratch/out_slash.txt");
out.open("w");
out.write(output.join("\n"));
out.close();

