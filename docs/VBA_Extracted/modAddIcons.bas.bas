' Module: modAddIcons.bas
' Type: Standard Module
' Stream Path: VBA/modAddIcons
' =========================================================

Attribute VB_Name = "modAddIcons"
''Build 026
''***************************************************************************
''
'' Authors:  JKP Application Development Services, info@jkp-ads.com, http://www.jkp-ads.com
''           Peter Thornton, pmbthornton@gmail.com
''
'' (c)2013-2015, all rights reserved to the authors
''
'' You are free to use and adapt the code in these modules for
'' your own purposes and to distribute as part of your overall project.
'' However all headers and copyright notices should remain intact
''
'' You may not publish the code in these modules, for example on a web site,
'' without the explicit consent of the authors
''***************************************************************************
'
'Option Explicit
'
'Sub ImageBoxAdder()
''-------------------------------------------------------------------------
'' Procedure : ImageBoxAdder
'' Author    : Peter Thornton
'' Created   : 26-01-2013
'' Purpose   : A macro to add icon images at design time to a Frame
''-------------------------------------------------------------------------
'    Dim i As Long
'    Dim lt As Single, tp As Single
'    Dim arrIcons()
'    Dim uf As UserForm
'    Dim fm As MSForms.Frame
'    Dim img As MSForms.Image
'    Dim sPath As String
'    Dim sFile As String
'
'    ' In Windows ideally the images should be 16x16 pixels to fit 12x12 points
'    ' ensure the images are "masked" in transparent areas, or make background colour same as
'    ' the treeview's background, typically white
'    '
'    ' if after adding images with this code the images masked areas do not appear transparent,
'    ' manually re-add from file, from the image control's Picture property
'    '
'    ' In Mac ideally the images should be about 20x20.
'    ' They must be 8 bit/256 colours or less and not masked with a transparent colour
'    ' (to make the images in this demo portable between Windows & Mac they have not been given transparent atributes)
'
'
'    sPath = ThisWorkbook.Path & "\Images\"
'
'    arrIcons = FileNames    ' get the file names
'
'    Set uf = ThisWorkbook.VBProject.VBComponents("ufDemoIcons").designer
'    Set fm = uf.Controls("frmImageBox")    ' ensure the form has a similarly named Frame
'
'    ' if starting afresh remove existing images
'    For i = fm.Controls.Count - 1 To 0 Step -1
'        '   fm.Controls.Remove i  '
'    Next
'
'    tp = fm.Controls.Count * 15 + 1.5
'
'    For i = 0 To UBound(arrIcons)
'        sFile = sPath & arrIcons(i)
'
'        Set img = fm.Controls.Add("forms.image.1")
'
'        With img
'            .BackStyle = fmBackStyleTransparent    ' needed to see through transparent
'            .Left = 1.5
'            .Top = tp
'            .Width = 12
'            .Height = 12
'            .Picture = LoadPicture(sFile)
'            .BackStyle = fmBackStyleTransparent
'            .Name = Left$(arrIcons(i), Len(arrIcons(i)) - 4)
'        End With
'        tp = tp + 15
'    Next
'
'    fm.Height = tp + 3
'
'End Sub
'
'Function FileNames()
'' these are the original file names of images loaded to the demo form
'
'    FileNames = Array( _
'                "FLGBRAZL.gif", "FLGCAN.gif", "FLGFRAN.gif", "FLGGERM.gif", _
'                "FLGNETH.gif", "FLGSWED.gif", "FLGUK.gif", "FLGUSA02.gif", _
'                "NOTE03.gif", "NOTE04.gif", "OpenBook.gif", _
'                "FolderOpen.gif", "FolderClosed.gif", _
'                "GreenTick.gif", "Scroll.gif")
'
'End Function
