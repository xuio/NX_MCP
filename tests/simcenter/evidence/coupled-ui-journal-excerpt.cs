// Extract from native UI journal; original SHA256 31a31b8a9a0bf6ba14259e3d2bff7fd4157d11cf6459d5d1dcbe2e6ae2489a5f
// Evidence excerpt only, not a runnable journal. Original line numbers preserved.

// 5727:     NXOpen.CAE.SimSolution simSolution1;
// 5728:     simSolution1 = simSimulation1.CreateSolution("NX MULTIPHYSICS", "Coupled Thermal-Flow", "Thermal-Flow", "Solution 1Native UI Environment Reference", NXOpen.CAE.SimSimulation.AxisymAbstractionType.None);
// 5729:     
// 5730:     NXOpen.CAE.PropertyTable propertyTable1;
// 5731:     propertyTable1 = simSolution1.PropertyTable;
// 5732:     
// 5733:     NXOpen.CAE.CaePart caePart1 = ((NXOpen.CAE.CaePart)workSimPart);
// 5734:     NXOpen.CAE.ModelingObjectPropertyTable modelingObjectPropertyTable1;
// 5735:     modelingObjectPropertyTable1 = caePart1.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Thermal Parameters", "NX MULTIPHYSICS - Coupled Thermal-Flow", "NX MULTIPHYSICS", "Thermal Solution Parameters1", 1);
// 5736:     
// 5737:     NXOpen.CAE.CaePart caePart2 = ((NXOpen.CAE.CaePart)workSimPart);
// 5738:     NXOpen.CAE.ModelingObjectPropertyTable modelingObjectPropertyTable2;
// 5739:     modelingObjectPropertyTable2 = caePart2.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Flow Solution Parameters", "NX MULTIPHYSICS - Coupled Thermal-Flow", "NX MULTIPHYSICS", "Flow Solution Parameters1", 2);
// 5740:     
// 5741:     NXOpen.CAE.CaePart caePart3 = ((NXOpen.CAE.CaePart)workSimPart);
// 5742:     NXOpen.CAE.ModelingObjectPropertyTable modelingObjectPropertyTable3;
// 5743:     modelingObjectPropertyTable3 = caePart3.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Flow Surface Parameters", "NX MULTIPHYSICS - Coupled Thermal-Flow", "NX MULTIPHYSICS", "Flow Surface Parameters1", 3);
// 5744:     
// 5745:     NXOpen.CAE.CaePart caePart4 = ((NXOpen.CAE.CaePart)workSimPart);
// 5746:     NXOpen.CAE.ModelingObjectPropertyTable modelingObjectPropertyTable4;
// 5747:     modelingObjectPropertyTable4 = caePart4.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Thermal-Flow Coupled Solution Parameters", "NX MULTIPHYSICS - Coupled Thermal-Flow", "NX MULTIPHYSICS", "Thermal-Flow Coupled Solution Parameters1", 4);
// 5748:     
// 5749:     NXOpen.CAE.CaePart caePart5 = ((NXOpen.CAE.CaePart)workSimPart);
// 5750:     NXOpen.CAE.ModelingObjectPropertyTable modelingObjectPropertyTable5;
// 5751:     modelingObjectPropertyTable5 = caePart5.ModelingObjectPropertyTables.CreateModelingObjectPropertyTable("Thermal-Flow Output Requests", "NX MULTIPHYSICS - Coupled Thermal-Flow", "NX MULTIPHYSICS", "Thermal-Flow Output Requests1", 5);

// 10422:     NXOpen.CAE.PropertyTable propertyTable2;
// 10423:     propertyTable2 = simSolution1.PropertyTable;
// 10424:     
// 10425:     propertyTable2.SetIntegerPropertyValue("Solver Type", 6);
// 10426:     
// 10427:     propertyTable2.SetNamedPropertyTablePropertyValue("Thermal Parameters", modelingObjectPropertyTable1);
// 10428:     
// 10429:     propertyTable2.SetNamedPropertyTablePropertyValue("Flow Solution Parameters", modelingObjectPropertyTable2);
// 10430:     
// 10431:     propertyTable2.SetNamedPropertyTablePropertyValue("Flow Surface Parameters", modelingObjectPropertyTable3);
// 10432:     
// 10433:     propertyTable2.SetNamedPropertyTablePropertyValue("Coupled Solution Parameters", modelingObjectPropertyTable4);
// 10434:     
// 10435:     propertyTable2.SetStringPropertyValue("Mass", "kg");
// 10436:     
// 10437:     propertyTable2.SetStringPropertyValue("Length", "mm");
// 10438:     
// 10439:     propertyTable2.SetStringPropertyValue("Time Solution Units", "second");
// 10440:     
// 10441:     propertyTable2.SetStringPropertyValue("Power", "microWatt");
// 10442:     
// 10443:     propertyTable2.SetStringPropertyValue("Heat Flux", "microW/mm^2");
// 10444:     
// 10445:     propertyTable2.SetStringPropertyValue("Energy", "microJoule");
// 10446:     
// 10447:     propertyTable2.SetStringPropertyValue("Velocity", "mm/s");
// 10448:     
// 10449:     propertyTable2.SetStringPropertyValue("Pressure", "mN/mm^2");
// 10450:     
// 10451:     propertyTable2.SetStringPropertyValue("Viscosity", "kg/mm-s");
// 10452:     
// 10453:     propertyTable2.SetStringPropertyValue("Density", "kg/mm^3");
// 10454:     
// 10455:     propertyTable2.SetStringPropertyValue("Specific Heat", "microJ/kg-C");
// 10456:     
// 10457:     propertyTable2.SetStringPropertyValue("Force", "mN");
// 10458:     
// 10459:     NXOpen.Fields.ScalarFieldWrapper scalarFieldWrapper1;
// 10460:     scalarFieldWrapper1 = propertyTable2.GetScalarFieldWrapperPropertyValue("Absolute Pressure");
// 10461:     
// 10462:     NXOpen.Expression expression1;
// 10463:     expression1 = scalarFieldWrapper1.GetExpression();
// 10464:     
// 10465:     NXOpen.Unit unit1 = ((NXOpen.Unit)workSimPart.UnitCollection.FindObject("PressureNewtonPerSquareMilliMeter"));
// 10466:     workSimPart.Expressions.EditWithUnits(expression1, unit1, "0.101325");
// 10467:     
// 10468:     scalarFieldWrapper1.SetExpression(expression1);
// 10469:     
// 10470:     propertyTable2.SetScalarFieldWrapperPropertyValue("Absolute Pressure", scalarFieldWrapper1);

// 28767:     propertyTable4.SetIntegerPropertyValue("Solution Type", 0);
// 28768:     
// 28769:     NXOpen.Unit unit2 = ((NXOpen.Unit)workSimPart.UnitCollection.FindObject("Second"));
// 28770:     propertyTable4.SetBaseScalarWithDataPropertyValue("End Time", "0", unit2);
// 28771:     
// 28772:     int nErrs2;
// 28773:     nErrs2 = theSession.UpdateManager.DoUpdate(markId14);

// 30543:     theCAESimSolveManager.SolveChainOfSolutions(psolutions2, NXOpen.CAE.SimSolution.SolveOption.WriteSolverInputFile, NXOpen.CAE.SimSolution.SetupCheckOption.CompleteCheckAndOutputErrors, NXOpen.CAE.SimSolution.SolveMode.Background, out numsolutionssolved2, out numsolutionsfailed2, out numsolutionsskipped2);
