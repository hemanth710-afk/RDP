
var output = [];
try {
    app.newProject();
    var footageFile = new File("C:\\Users\\L.Thirumala Teja\\Downloads\\fragment - slowed - slxughter.mp3");
    if (!footageFile.exists) throw new Error("File not found");
    var importOptions = new ImportOptions(footageFile);
    var footage = app.project.importFile(importOptions);
    output.push("Import success: " + footage.name);
} catch (e) {
    output.push("Error: " + e.toString());
}
var out_file = new File("C:\\Users\\L.Thirumala Teja\\AI_EDITOR\\scratch\\out_import.txt");
out_file.open("w");
out_file.write(output.join("\n"));
out_file.close();

