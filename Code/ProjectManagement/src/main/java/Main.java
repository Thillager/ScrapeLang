import javax.swing.*;
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Main {
	public static void main(String[] args) {
		JFrame frame = new JFrame("Scrape Project Manager");
		JPanel panel = new JPanel();
		JButton newProject = new JButton("Neues Projekt");
		JFileChooser chooser = new JFileChooser();
		JTextField projektName = new JTextField(20);


		chooser.setDialogTitle("Bitte einen Ordner auswählen");
		chooser.setFileSelectionMode(JFileChooser.DIRECTORIES_ONLY);


		newProject.addActionListener(e -> {
				String ProjektName;
				ProjektName = projektName.getText();
				int ergebnis = chooser.showOpenDialog(frame);
				if (ergebnis == JFileChooser.APPROVE_OPTION) {
					File ausgewaehlterOrdner = chooser.getSelectedFile();
					Path basisPfad = ausgewaehlterOrdner.toPath();
					System.out.println("Ausgewählter Pfad: " + ausgewaehlterOrdner.getAbsolutePath());
					try {
						Files.createDirectories(basisPfad.resolve(ProjektName + "/out"));
						Path configDatei = basisPfad.resolve(ProjektName + "/settings.json");
						if (!Files.exists(configDatei)) {
							Files.createFile(configDatei);
							String dateiInhalt = """
							{
								"Transpiler": "Transpiler",
								"input": "src/spiel.scrape",
								"output": "out/spiel.sb3"
							}
							""";

							Files.writeString(configDatei, dateiInhalt);

						}
					} catch (Exception f){
						System.out.println(e);
					}
				} else {
					System.out.println("Auswahl abgebrochen.");
				}
			});


		panel.add(projektName);
		panel.add(newProject);


		frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
		frame.setSize(1200, 800);
		frame.add(panel);
		frame.setVisible(true);
	}
}
