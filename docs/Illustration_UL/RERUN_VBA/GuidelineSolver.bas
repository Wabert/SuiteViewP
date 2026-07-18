Attribute VB_Name = "GuidelineSolver"
Attribute VB_Base = "0{A2D2C69E-4445-466D-A6C5-7D4C676EA549}{A49EFD4D-7777-429A-8650-C7EADA0C340B}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private Sub Form_Open(Cancel As Integer)
    If Range("sINPUT_TAMRA_Force").Value = True Then GuidelineSolver.ckbx_TAMRA = True Else GuidelineSolver.ckbx_TAMRA = False
    If Range("sINPUT_TEFRA_Force").Value = True Then GuidelineSolver.ckbx_TEFRA = True Else GuidelineSolver.ckbx_TEFRA = False
End Sub

Private Sub btn_Go_Click()
    
    Dim StartYear As Integer
    Dim StopYear As Integer
    
    ' Set the first year & last year to evaluate the Guidelines
    If GuidelineSolver.ckbx_Recal_All_Years = True Then
        StartYear = 1
        StopYear = 121 - Range("sINPUT_Issue_Age").Value
    Else
        StartYear = GuidelineSolver.txtbx_From_Year.Value
        StopYear = GuidelineSolver.txtbx_From_Year.Value
    End If
    
    'Pass arguements to GuidelineRecal Function
    GuidelineRecal StartYear, 121, GuidelineSolver.ckbx_TEFRA, GuidelineSolver.ckbx_TAMRA, False
    
    
End Sub

Private Sub ckbx_Recal_All_Years_Click()
    If GuidelineSolver.ckbx_Recal_All_Years = True Then
       GuidelineSolver.lbl_From_Year.Visible = False
       GuidelineSolver.lbl_To_Year.Visible = False
       GuidelineSolver.txtbx_From_Year.Visible = False
       GuidelineSolver.txtbx_To_Year.Visible = False
    Else
       GuidelineSolver.lbl_From_Year.Visible = True
       GuidelineSolver.lbl_To_Year.Visible = True
       GuidelineSolver.txtbx_From_Year.Visible = True
       GuidelineSolver.txtbx_To_Year.Visible = True
    End If
End Sub

Private Sub UserForm_activate()
    If Range("sINPUT_TAMRA_Force").Value = True Then GuidelineSolver.ckbx_TAMRA = True Else GuidelineSolver.ckbx_TAMRA = False
    If Range("sINPUT_TEFRA_Force").Value = True Then GuidelineSolver.ckbx_TEFRA = True Else GuidelineSolver.ckbx_TEFRA = False
    GuidelineSolver.ckbx_Recal_All_Years = True
    GuidelineSolver.lbl_From_Year.Visible = False
    GuidelineSolver.lbl_To_Year.Visible = False
    GuidelineSolver.txtbx_From_Year.Visible = False
    GuidelineSolver.txtbx_To_Year.Visible = False
End Sub





