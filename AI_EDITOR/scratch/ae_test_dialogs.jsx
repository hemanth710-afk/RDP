
var output = [];
try {
    app.newProject();
    var footageFile = new File("C:\\Users\\L.Thirumala Teja\\Downloads\\fragment - slowed - slxughter.mp3");
    var importOptions = new ImportOptions(footageFile);
    app.beginSuppressDialogs();
    var footage = app.project.importFile(importOptions);
    var dialogs = app.endSuppressDialogs(false);
    output.push("Dialogs for MP3: " + dialogs);
    
    var footageFile2 = new File("C:\\Users\\L.Thirumala Teja\\Downloads\\Naruto Vs Sasuke-2x-RIFE-RIFE4.0-120fps.mp4");
    var importOptions2 = new ImportOptions(footageFile2);
    app.beginSuppressDialogs();
    var footage2 = app.project.importFile(importOptions2);
    var dialogs2 = app.endSuppressDialogs(false);
    output.push("Dialogs for MP4: " + dialogs2);
} catch (e) {
    output.push("Error: " + e.toString());
}
var out_file = new File("C:\\Users\\L.Thirumala Teja\\AI_EDITOR\\scratch\\out_dialogs.txt");
out_file.open("w");
out_file.write(output.join("\n"));
out_file.close();

